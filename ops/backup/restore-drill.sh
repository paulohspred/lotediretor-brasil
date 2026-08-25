#!/usr/bin/env bash
set -euo pipefail

SRC="${1:?usage: ops/backup/restore-drill.sh backups/<timestamp>}"
PLATFORM_OWNER="${PLATFORM_DB_MIGRATION_USER:-lotediretor}"
CONTROL_OWNER="${CONTROL_DB_MIGRATION_USER:-lotediretor_control}"
ENVIRONMENT="${DEPLOY_ENVIRONMENT:-${NODE_ENV:-local}}"
STAMP="$(basename "$SRC")"
START_EPOCH=$(date +%s)

test -f "$SRC/platform.dump" && test -f "$SRC/control.dump" && test -f "$SRC/SHA256SUMS.txt"
( cd "$SRC" && sha256sum -c SHA256SUMS.txt )

PDB="ld_restore_platform_$$"
CDB="ld_restore_control_$$"
cleanup(){
  docker compose exec -T platform-db psql -U "$PLATFORM_OWNER" -d postgres -c "DROP DATABASE IF EXISTS $PDB WITH (FORCE)" >/dev/null 2>&1 || true
  docker compose exec -T control-db psql -U "$CONTROL_OWNER" -d postgres -c "DROP DATABASE IF EXISTS $CDB WITH (FORCE)" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

docker compose exec -T platform-db createdb -U "$PLATFORM_OWNER" "$PDB"
docker compose exec -T control-db createdb -U "$CONTROL_OWNER" "$CDB"
cat "$SRC/platform.dump" | docker compose exec -T platform-db pg_restore -U "$PLATFORM_OWNER" -d "$PDB" --no-owner --no-acl
cat "$SRC/control.dump" | docker compose exec -T control-db pg_restore -U "$CONTROL_OWNER" -d "$CDB" --no-owner --no-acl

docker compose exec -T platform-db psql -v ON_ERROR_STOP=1 -U "$PLATFORM_OWNER" -d "$PDB" -c "select count(*) from public.schema_migrations" >/dev/null
docker compose exec -T control-db psql -v ON_ERROR_STOP=1 -U "$CONTROL_OWNER" -d "$CDB" -c "select count(*) from public.schema_migrations" >/dev/null
RTO_SECONDS=$(( $(date +%s) - START_EPOCH ))

docker compose exec -T control-db psql -U "$CONTROL_OWNER" -d "${CONTROL_DB_NAME:-lotediretor_control}" -v ON_ERROR_STOP=1 -v stamp="$STAMP" -v env_name="$ENVIRONMENT" -v src="$SRC" -v rto="$RTO_SECONDS" <<'SQL'
INSERT INTO ops.restore_run(backup_run_id,scope,environment,status,target_ref,evidence,completed_at,idempotency_key)
VALUES((SELECT id FROM ops.backup_run WHERE idempotency_key='backup:'||:'stamp'),'FULL',:'env_name','SUCCEEDED',:'src',jsonb_build_object('platform_restore','PASS','control_restore','PASS','schema_migrations_verified',true),now(),'restore:'||:'stamp')
ON CONFLICT(idempotency_key) DO UPDATE SET status='SUCCEEDED',target_ref=excluded.target_ref,evidence=excluded.evidence,completed_at=now(),error=null;
INSERT INTO ops.dr_drill(environment,status,scenario,rto_seconds,evidence,started_at,completed_at,idempotency_key)
VALUES(:'env_name','PASSED','full_database_restore',:'rto'::integer,jsonb_build_object('backup_stamp',:'stamp','platform_restore','PASS','control_restore','PASS'),now()-( :'rto'::integer * interval '1 second'),now(),'dr:'||:'stamp')
ON CONFLICT(idempotency_key) DO UPDATE SET status='PASSED',rto_seconds=excluded.rto_seconds,evidence=excluded.evidence,completed_at=now();
SQL

echo "Restore drill PASS: database dumps restored into temporary databases (RTO ${RTO_SECONDS}s)."
