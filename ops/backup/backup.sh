#!/usr/bin/env bash
set -euo pipefail

STAMP="${1:-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${BACKUP_DIR:-./backups}/$STAMP"
PLATFORM_OWNER="${PLATFORM_DB_MIGRATION_USER:-lotediretor}"
CONTROL_OWNER="${CONTROL_DB_MIGRATION_USER:-lotediretor_control}"
ENVIRONMENT="${DEPLOY_ENVIRONMENT:-${NODE_ENV:-local}}"
START_EPOCH=$(date +%s)
START_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
mkdir -p "$OUT"

echo "Creating database dumps in $OUT"
docker compose exec -T platform-db pg_dump -Fc -U "$PLATFORM_OWNER" "${PLATFORM_DB_NAME:-lotediretor}" > "$OUT/platform.dump"
docker compose exec -T control-db pg_dump -Fc -U "$CONTROL_OWNER" "${CONTROL_DB_NAME:-lotediretor_control}" > "$OUT/control.dump"

docker compose run --rm --no-deps -v "$(cd "$OUT" && pwd):/backup" --entrypoint /bin/sh minio-init -c \
  "mc alias set local http://minio:9000 '${S3_ACCESS_KEY:-lotediretor}' '${S3_SECRET_KEY:-lotediretor-local-secret}' >/dev/null && mkdir -p /backup/object-storage && mc mirror --overwrite local/'${S3_BUCKET:-lotediretor}' /backup/object-storage"

CAPTURE_END_EPOCH=$(date +%s)
CAPTURE_END_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
cat > "$OUT/METADATA.txt" <<META
backup_started_at_utc=$START_ISO
backup_completed_at_utc=$CAPTURE_END_ISO
backup_started_epoch=$START_EPOCH
backup_completed_epoch=$CAPTURE_END_EPOCH
project_version=$(cat VERSION 2>/dev/null || echo unknown)
platform_db=${PLATFORM_DB_NAME:-lotediretor}
control_db=${CONTROL_DB_NAME:-lotediretor_control}
s3_bucket=${S3_BUCKET:-lotediretor}
META

# Metadata is part of the immutable checksum set. Never append files that are
# required to reconstruct the restore point before this manifest is generated.
( cd "$OUT" && find . -type f ! -name SHA256SUMS.txt -print0 | sort -z | xargs -0 -r sha256sum > SHA256SUMS.txt )
TOTAL_BYTES=$(du -sb "$OUT" | awk '{print $1}')
CAPTURE_WINDOW_SECONDS=$((CAPTURE_END_EPOCH-START_EPOCH))

docker compose exec -T control-db psql -U "$CONTROL_OWNER" -d "${CONTROL_DB_NAME:-lotediretor_control}" -v ON_ERROR_STOP=1 \
  -v stamp="$STAMP" -v backup_ref="$OUT" -v env_name="$ENVIRONMENT" -v total_bytes="$TOTAL_BYTES" \
  -v started_epoch="$START_EPOCH" -v completed_epoch="$CAPTURE_END_EPOCH" -v capture_window="$CAPTURE_WINDOW_SECONDS" <<'SQL'
INSERT INTO ops.backup_run(scope,environment,status,backup_ref,checksum_manifest,size_bytes,started_at,completed_at,idempotency_key)
VALUES(
  'FULL',:'env_name','SUCCEEDED',:'backup_ref',
  jsonb_build_object(
    'manifest','SHA256SUMS.txt','stamp',:'stamp','metadata','METADATA.txt',
    'backup_started_epoch',:'started_epoch'::bigint,'backup_completed_epoch',:'completed_epoch'::bigint,
    'capture_window_seconds',:'capture_window'::integer,'object_storage_included',true
  ),
  :'total_bytes'::bigint,to_timestamp(:'started_epoch'::bigint),to_timestamp(:'completed_epoch'::bigint),'backup:'||:'stamp'
)
ON CONFLICT(idempotency_key) DO UPDATE SET
  status='SUCCEEDED',backup_ref=excluded.backup_ref,checksum_manifest=excluded.checksum_manifest,
  size_bytes=excluded.size_bytes,started_at=excluded.started_at,completed_at=excluded.completed_at,error=null;
SQL

echo "Backup complete: $OUT (capture window ${CAPTURE_WINDOW_SECONDS}s)"

if [[ "${BACKUP_RETENTION_DAYS:-0}" =~ ^[0-9]+$ ]] && (( BACKUP_RETENTION_DAYS > 0 )); then
  find "${BACKUP_DIR:-./backups}" -mindepth 1 -maxdepth 1 -type d -mtime "+${BACKUP_RETENTION_DAYS}" -print -exec rm -rf {} +
fi
