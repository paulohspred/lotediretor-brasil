#!/usr/bin/env bash
set -euo pipefail

SRC="${1:?usage: ops/backup/restore-drill.sh backups/<timestamp>}"
PLATFORM_OWNER="${PLATFORM_DB_MIGRATION_USER:-lotediretor}"
CONTROL_OWNER="${CONTROL_DB_MIGRATION_USER:-lotediretor_control}"

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

echo "Restore drill PASS: database dumps restored into temporary databases."
