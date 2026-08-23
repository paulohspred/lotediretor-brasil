#!/usr/bin/env bash
set -euo pipefail
STAMP="${1:-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${BACKUP_DIR:-./backups}/$STAMP"
mkdir -p "$OUT"
echo "Creating database dumps in $OUT"
docker compose exec -T platform-db pg_dump -Fc -U "${PLATFORM_DB_MIGRATION_USER:-lotediretor}" "${PLATFORM_DB_NAME:-lotediretor}" > "$OUT/platform.dump"
docker compose exec -T control-db pg_dump -Fc -U "${CONTROL_DB_USER:-lotediretor_control}" "${CONTROL_DB_NAME:-lotediretor_control}" > "$OUT/control.dump"
# Object storage is mirrored to the host using a transient mc container.
docker compose run --rm --no-deps -v "$(cd "$OUT" && pwd):/backup" --entrypoint /bin/sh minio-init -c \
  "mc alias set local http://minio:9000 '${S3_ACCESS_KEY:-lotediretor}' '${S3_SECRET_KEY:-lotediretor-local-secret}' >/dev/null && mkdir -p /backup/object-storage && mc mirror --overwrite local/'${S3_BUCKET:-lotediretor}' /backup/object-storage"
( cd "$OUT" && find . -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS.txt )
cat > "$OUT/METADATA.txt" <<META
created_at_utc=$STAMP
project_version=$(cat VERSION 2>/dev/null || echo unknown)
platform_db=${PLATFORM_DB_NAME:-lotediretor}
control_db=${CONTROL_DB_NAME:-lotediretor_control}
s3_bucket=${S3_BUCKET:-lotediretor}
META
echo "Backup complete: $OUT"
# Optional local retention after a successful backup.
if [[ "${BACKUP_RETENTION_DAYS:-0}" =~ ^[0-9]+$ ]] && (( BACKUP_RETENTION_DAYS > 0 )); then
  find "${BACKUP_DIR:-./backups}" -mindepth 1 -maxdepth 1 -type d -mtime "+${BACKUP_RETENTION_DAYS}" -print -exec rm -rf {} +
fi
