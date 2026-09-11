#!/usr/bin/env bash
set -euo pipefail

DB_USER="${PLATFORM_DB_MIGRATION_USER:-lotediretor}"
DB_NAME="${PLATFORM_DB_NAME:-lotediretor}"
TENANT_ID="00000000-0000-4000-8000-000000000099"
IDEM_KEY="reliability-expired-reclaim"
OUTBOX_ID=""

psql_platform() {
  docker compose exec -T platform-db psql -X -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" "$@"
}

cleanup() {
  psql_platform -q -c "delete from api.idempotency_key where tenant_id='$TENANT_ID'::uuid and scope='reliability.runtime' and idempotency_key='$IDEM_KEY';" >/dev/null 2>&1 || true
  if [[ -n "$OUTBOX_ID" ]]; then
    psql_platform -q -c "delete from event.outbox where id='$OUTBOX_ID'::uuid;" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

printf 'Proving expired idempotency keys are atomically reclaimable...\n'
psql_platform -q -c "delete from api.idempotency_key where tenant_id='$TENANT_ID'::uuid and scope='reliability.runtime' and idempotency_key='$IDEM_KEY';"
psql_platform -q -c "
  insert into api.idempotency_key(tenant_id,scope,idempotency_key,status,response,completed_at,expires_at)
  values('$TENANT_ID'::uuid,'reliability.runtime','$IDEM_KEY','COMPLETED','{\"stale\":true}'::jsonb,now()-interval '2 hours',now()-interval '1 hour');
"

reclaimed="$(psql_platform -qAt -c "
  insert into api.idempotency_key(tenant_id,scope,idempotency_key,status,response,completed_at,expires_at)
  values('$TENANT_ID'::uuid,'reliability.runtime','$IDEM_KEY','IN_PROGRESS',null,null,now()+interval '24 hours')
  on conflict (tenant_id,scope,idempotency_key) do update
  set status='IN_PROGRESS',response=null,created_at=now(),completed_at=null,expires_at=excluded.expires_at
  where api.idempotency_key.expires_at<=now()
  returning status||'|'||(response is null)::text||'|'||(completed_at is null)::text;
")"
if [[ "$reclaimed" != "IN_PROGRESS|true|true" ]]; then
  printf 'Expired idempotency reclaim failed: %s\n' "$reclaimed" >&2
  exit 1
fi

printf 'Proving crash-stuck PUBLISHING outbox rows are reclaimed by lease...\n'
OUTBOX_ID="$(psql_platform -qAt -c "
  insert into event.outbox(topic,aggregate_type,aggregate_id,payload,status,attempts,next_attempt_at,claimed_by,claimed_at,lease_until)
  values('analysis.reliability.probe','reliability_probe','runtime','{\"synthetic\":true,\"purpose\":\"outbox_lease_recovery\"}'::jsonb,
         'PUBLISHING',1,now(),'crashed-dispatcher',now()-interval '10 minutes',now()-interval '5 minutes')
  returning id;
")"

for _ in $(seq 1 45); do
  status="$(psql_platform -qAt -c "select status from event.outbox where id='$OUTBOX_ID'::uuid;")"
  if [[ "$status" == "PUBLISHED" ]]; then
    metadata="$(psql_platform -qAt -c "select coalesce(publish_metadata->>'stream','') from event.outbox where id='$OUTBOX_ID'::uuid;")"
    if [[ -z "$metadata" ]]; then
      printf 'Recovered outbox row was PUBLISHED without JetStream metadata.\n' >&2
      exit 1
    fi
    printf 'Reliability runtime integration: OK\n'
    exit 0
  fi
  sleep 1
done

psql_platform -x -c "select id,status,attempts,claimed_by,claimed_at,lease_until,last_error,publish_metadata from event.outbox where id='$OUTBOX_ID'::uuid;" >&2 || true
printf 'Dispatcher did not reclaim the stale PUBLISHING row within 45 seconds.\n' >&2
exit 1
