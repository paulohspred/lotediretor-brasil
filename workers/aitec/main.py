from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

import psycopg
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from psycopg.types.json import Jsonb

DB = os.environ['PLATFORM_DATABASE_URL']
ENGINE = os.getenv('AITEC_ENGINE_INTERNAL_URL', 'http://aitec-engine:8002').rstrip('/')
TOKEN = os.environ['INTERNAL_API_TOKEN']
POLL_SECONDS = max(0.2, float(os.getenv('AITEC_JOB_POLL_SECONDS', '1')))
TIMEOUT_SECONDS = max(5.0, float(os.getenv('AITEC_JOB_TIMEOUT_SECONDS', '180')))
MAX_ATTEMPTS = max(1, int(os.getenv('AITEC_JOB_MAX_ATTEMPTS', '3')))
STALE_SECONDS = max(60, int(os.getenv('AITEC_JOB_STALE_SECONDS', '600')))
MAX_RESPONSE_BYTES = max(1024, int(os.getenv('AITEC_JOB_MAX_RESPONSE_BYTES', str(32 * 1024 * 1024))))
METRICS_PORT = max(1, int(os.getenv('AITEC_METRICS_PORT', '9104')))
METRICS_REFRESH_SECONDS = max(1.0, float(os.getenv('AITEC_METRICS_REFRESH_SECONDS', '5')))

JOB_STATES = ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')
JOB_STATE = Gauge('lotediretor_aitec_jobs', 'Persisted A.I TEC jobs by status.', ['status'])
OLDEST_JOB_AGE = Gauge('lotediretor_aitec_oldest_job_age_seconds', 'Age in seconds of the oldest A.I TEC job in each status.', ['status'])
JOB_EXECUTIONS = Counter('lotediretor_aitec_job_executions_total', 'A.I TEC worker execution outcomes.', ['result'])
STALE_RECLAIMS = Counter('lotediretor_aitec_job_stale_reclaims_total', 'Stale RUNNING A.I TEC jobs reclaimed by the worker.', ['result'])
ENGINE_DURATION = Histogram(
    'lotediretor_aitec_engine_duration_seconds',
    'Time spent waiting for an A.I TEC engine execution.',
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 180),
)
WORKER_LOOP_ERRORS = Counter('lotediretor_aitec_worker_loop_errors_total', 'Unhandled A.I TEC worker loop errors.')
LAST_DB_SUCCESS = Gauge('lotediretor_aitec_worker_last_db_success_unixtime', 'Unix timestamp of the last successful A.I TEC worker database cycle.')
WORKER_READY = Gauge('lotediretor_aitec_worker_ready', '1 after the A.I TEC worker metrics server has started.')
_last_metrics_refresh = 0.0


@dataclass
class EngineFailure(Exception):
    message: str
    retryable: bool

    def __str__(self) -> str:
        return self.message


def refresh_queue_metrics(conn: psycopg.Connection, force: bool = False) -> None:
    global _last_metrics_refresh
    now = time.monotonic()
    if not force and now - _last_metrics_refresh < METRICS_REFRESH_SECONDS:
        return
    rows = conn.execute(
        """select status,count(*)::int,
                  coalesce(max(extract(epoch from (now()-case when status='RUNNING' then coalesce(started_at,created_at) else created_at end))),0)::double precision
             from aitec.job
            where status in ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED')
            group by status"""
    ).fetchall()
    counts = {status: (0, 0.0) for status in JOB_STATES}
    for status, count, oldest_age in rows:
        counts[str(status)] = (int(count), max(0.0, float(oldest_age or 0.0)))
    for status, (count, oldest_age) in counts.items():
        JOB_STATE.labels(status=status).set(count)
        OLDEST_JOB_AGE.labels(status=status).set(oldest_age)
    LAST_DB_SUCCESS.set(time.time())
    _last_metrics_refresh = now


def reclaim_stale(conn: psycopg.Connection) -> None:
    with conn.transaction():
        rows = conn.execute(
            """update aitec.job
               set status=case when attempts >= %s then 'FAILED' else 'QUEUED' end,
                   error=case when attempts >= %s then coalesce(error,'worker_stale_after_max_attempts') else 'worker_stale_requeued' end,
                   completed_at=case when attempts >= %s then now() else null end
               where status='RUNNING' and started_at < now()-(%s||' seconds')::interval
               returning status""",
            (MAX_ATTEMPTS, MAX_ATTEMPTS, MAX_ATTEMPTS, str(STALE_SECONDS)),
        ).fetchall()
    for (status,) in rows:
        STALE_RECLAIMS.labels(result='failed' if status == 'FAILED' else 'requeued').inc()
    if rows:
        refresh_queue_metrics(conn, force=True)


def claim(conn: psycopg.Connection):
    with conn.transaction():
        row = conn.execute(
            """select id,tenant_id,project_id,constraint_snapshot_id,operation,args,kwargs,execution_context,attempts
               from aitec.job
               where status='QUEUED'
               order by created_at,id
               for update skip locked
               limit 1"""
        ).fetchone()
        if not row:
            return None
        jid = row[0]
        updated = conn.execute(
            """update aitec.job
               set status='RUNNING',attempts=attempts+1,started_at=now(),completed_at=null,error=null
               where id=%s
               returning attempts""",
            (jid,),
        ).fetchone()
        return {
            'id': str(row[0]),
            'tenant_id': str(row[1]),
            'project_id': str(row[2]),
            'constraint_snapshot_id': str(row[3]) if row[3] else None,
            'operation': row[4],
            'args': row[5] or [],
            'kwargs': row[6] or {},
            'context': row[7] or {},
            'attempts': int(updated[0]),
        }


def execute_engine(job: dict) -> dict:
    payload = json.dumps(
        {'args': job['args'], 'kwargs': job['kwargs'], 'context': job['context']},
        separators=(',', ':'),
        ensure_ascii=False,
    ).encode('utf-8')
    request = urllib.request.Request(
        f"{ENGINE}/aitec/v20/execute/{job['operation']}",
        data=payload,
        headers={'Content-Type': 'application/json', 'X-Internal-Token': TOKEN},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise EngineFailure('aitec_engine_response_too_large', False)
            if response.status < 200 or response.status >= 300:
                raise EngineFailure(f'aitec_engine_http_{response.status}', response.status >= 500 or response.status == 429)
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode('utf-8', 'replace')
        raise EngineFailure(f'aitec_engine_http_{exc.code}:{detail}', exc.code >= 500 or exc.code == 429) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise EngineFailure(f'aitec_engine_unreachable:{exc}', True) from exc

    try:
        data = json.loads(raw)
    except Exception as exc:
        raise EngineFailure('aitec_engine_invalid_json', False) from exc
    if data.get('status') != 'EXECUTED' or data.get('operation') != job['operation']:
        raise EngineFailure('aitec_engine_contract_mismatch', False)
    context = data.get('context') or {}
    if str(context.get('tenant_id') or '') != job['tenant_id'] or str(context.get('project_id') or '') != job['project_id']:
        raise EngineFailure('aitec_engine_context_mismatch', False)
    if job['constraint_snapshot_id'] and str(context.get('constraint_snapshot_id') or '') != job['constraint_snapshot_id']:
        raise EngineFailure('aitec_engine_constraint_context_mismatch', False)
    return data


def complete(conn: psycopg.Connection, job: dict, response: dict) -> None:
    with conn.transaction():
        result = conn.execute(
            """update aitec.job set status='COMPLETED',solver_version=%s,classification=%s,
                   professional_review_required=%s,engine_response=%s,error=null,completed_at=now()
               where id=%s and status='RUNNING'
               returning id""",
            (
                response.get('solver_version'),
                response.get('classification'),
                bool(response.get('professional_review_required')),
                Jsonb(response),
                job['id'],
            ),
        ).fetchone()
        if not result:
            raise RuntimeError('aitec_job_not_running_at_completion')
        conn.execute(
            """insert into event.outbox(tenant_id,topic,aggregate_type,aggregate_id,dedupe_key,payload,status,next_attempt_at)
               values(%s,'aitec.job.completed','aitec.job',%s,%s,%s,'PENDING',now())
               on conflict(dedupe_key) where dedupe_key is not null do nothing""",
            (
                job['tenant_id'],
                job['id'],
                f"aitec.job.completed:{job['id']}",
                Jsonb({
                    'jobId': job['id'],
                    'projectId': job['project_id'],
                    'operation': job['operation'],
                    'solverVersion': response.get('solver_version'),
                    'classification': response.get('classification'),
                }),
            ),
        )
    JOB_EXECUTIONS.labels(result='completed').inc()


def fail(conn: psycopg.Connection, job: dict, error: EngineFailure) -> bool:
    terminal = (not error.retryable) or job['attempts'] >= MAX_ATTEMPTS
    with conn.transaction():
        conn.execute(
            """update aitec.job
               set status=%s,error=%s,completed_at=case when %s then now() else null end
               where id=%s and status='RUNNING'""",
            ('FAILED' if terminal else 'QUEUED', str(error)[:2000], terminal, job['id']),
        )
        if terminal:
            conn.execute(
                """insert into event.outbox(tenant_id,topic,aggregate_type,aggregate_id,dedupe_key,payload,status,next_attempt_at)
                   values(%s,'aitec.job.failed','aitec.job',%s,%s,%s,'PENDING',now())
                   on conflict(dedupe_key) where dedupe_key is not null do nothing""",
                (
                    job['tenant_id'],
                    job['id'],
                    f"aitec.job.failed:{job['id']}",
                    Jsonb({'jobId': job['id'], 'projectId': job['project_id'], 'operation': job['operation'], 'error': str(error)[:1000]}),
                ),
            )
    JOB_EXECUTIONS.labels(result='failed' if terminal else 'retry').inc()
    return terminal


def process_one() -> bool:
    with psycopg.connect(DB) as conn:
        reclaim_stale(conn)
        refresh_queue_metrics(conn)
        job = claim(conn)
        if not job:
            LAST_DB_SUCCESS.set(time.time())
            return False
        try:
            with ENGINE_DURATION.time():
                response = execute_engine(job)
            complete(conn, job, response)
            refresh_queue_metrics(conn, force=True)
            print(f"aitec job completed id={job['id']} operation={job['operation']} solver={response.get('solver_version')}", flush=True)
        except EngineFailure as exc:
            terminal = fail(conn, job, exc)
            refresh_queue_metrics(conn, force=True)
            print(f"aitec job {'failed' if terminal else 'retry'} id={job['id']} error={exc}", flush=True)
        except Exception as exc:
            failure = EngineFailure(f'aitec_worker_internal_error:{type(exc).__name__}:{exc}', True)
            terminal = fail(conn, job, failure)
            refresh_queue_metrics(conn, force=True)
            print(f"aitec worker internal error id={job['id']} terminal={terminal} error={exc!r}", flush=True)
    LAST_DB_SUCCESS.set(time.time())
    return True


def main() -> None:
    start_http_server(METRICS_PORT, addr='0.0.0.0')
    WORKER_READY.set(1)
    print(
        f'aitec-worker engine={ENGINE} max_attempts={MAX_ATTEMPTS} stale_seconds={STALE_SECONDS} metrics_port={METRICS_PORT}',
        flush=True,
    )
    while True:
        try:
            if not process_one():
                time.sleep(POLL_SECONDS)
        except Exception as exc:
            WORKER_LOOP_ERRORS.inc()
            print(f'aitec worker loop error {exc!r}', flush=True)
            time.sleep(max(2.0, POLL_SECONDS))


if __name__ == '__main__':
    main()
