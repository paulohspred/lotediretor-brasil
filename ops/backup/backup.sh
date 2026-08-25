#!/usr/bin/env bash
set -euo pipefail

STAMP="${1:-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${BACKUP_DIR:-./backups}/$STAMP"
PLATFORM_OWNER="${PLATFORM_DB_MIGRATION_USER:-lotediretor}"
CONTROL_OWNER="${CONTROL_DB_MIGRATION_USER:-lotediretor_control}"
ENVIRONMENT="${DEPLOY_ENVIRONMENT:-${NODE_ENV:-local}}"
mkdir -p "$OUT"

echo "Creating database dumps in $OUT"
docker compose exec -T platform-db pg_dump -Fc -U "$PLATFORM_OWNER" "${PLATFORM_DB_NAME:-lotediretor}" > "$OUT/platform.dump"
docker compose exec -T control-db pg_dump -Fc -U "$CONTROL_OWNER" "${CONTROL_DB_NAME:-lotediretor_control}" > "$OUT/control.dump"

docker compose run --rm --no-deps -v "$(cd "$OUT" && pwd):/backup" --entrypoint /bin/sh minio-init -c \
  "mc alias set local http://minio:9000 '${S3_ACCESS_KEY:-lotediretor}' '${S3_SECRET_KEY:-lotediretor-local-secret}' >/dev/null && mkdir -p /backup/object-storage && mc mirror --overwrite local/'${S3_BUCKET:-lotediretor}' /backup/object-storage"

( cd "$OUT" && find . -type f ! -name SHA256SUMS.txt -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS.txt )
cat > "$OUT/METADATA.txt" <<META
created_at_utc=$STAMP
project_version=$(cat VERSION 2>/dev/null || echo unknown)
platform_db=${PLATFORM_DB_NAME:-lotediretor}
control_db=${CONTROL_DB_NAME:-lotediretor_control}
s3_bucket=${S3_BUCKET:-lotediretor}
META
TOTAL_BYTES=$(du -sb "$OUT" | awk '{print $1}')
docker compose exec -T control-db psql -U "$CONTROL_OWNER" -d "${CONTROL_DB_NAME:-lotediretor_control}" -v ON_ERROR_STOP=1 -v stamp="$STAMP" -v backup_ref="$OUT" -v env_name="$ENVIRONMENT" -v total_bytes="$TOTAL_BYTES" <<'SQL'
INSERT INTO ops.backup_run(scope,environment,status,backup_ref,checksum_manifest,size_bytes,completed_at,idempotency_key)
VALUES('FULL',:'env_name','SUCCEEDED',:'backup_ref',jsonb_build_object('manifest','SHA256SUMS.txt','stamp',:'stamp'),:'total_bytes'::bigint,now(),'backup:'||:'stamp')
ON CONFLICT(idempotency_key) DO UPDATE SET status='SUCCEEDED',backup_ref=excluded.backup_ref,checksum_manifest=excluded.checksum_manifest,size_bytes=excluded.size_bytes,completed_at=now(),error=null;
SQL

echo "Backup complete: $OUT"

if [[ "${BACKUP_RETENTION_DAYS:-0}" =~ ^[0-9]+$ ]] && (( BACKUP_RETENTION_DAYS > 0 )); then
  find "${BACKUP_DIR:-./backups}" -mindepth 1 -maxdepth 1 -type d -mtime "+${BACKUP_RETENTION_DAYS}" -print -exec rm -rf {} +
fi
