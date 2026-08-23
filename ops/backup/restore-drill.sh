#!/usr/bin/env bash
set -euo pipefail
SRC="${1:?usage: ops/backup/restore-drill.sh backups/<timestamp>}"
test -f "$SRC/platform.dump" && test -f "$SRC/control.dump"
( cd "$SRC" && sha256sum -c SHA256SUMS.txt )
PDB="ld_restore_platform_$$"; CDB="ld_restore_control_$$"
cleanup(){
 docker compose exec -T platform-db psql -U "${PLATFORM_DB_MIGRATION_USER:-lotediretor}" -d postgres -c "DROP DATABASE IF EXISTS $PDB WITH (FORCE)" >/dev/null 2>&1 || true
 docker compose exec -T control-db psql -U "${CONTROL_DB_USER:-lotediretor_control}" -d postgres -c "DROP DATABASE IF EXISTS $CDB WITH (FORCE)" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup
docker compose exec -T platform-db createdb -U "${PLATFORM_DB_MIGRATION_USER:-lotediretor}" "$PDB"
docker compose exec -T control-db createdb -U "${CONTROL_DB_USER:-lotediretor_control}" "$CDB"
cat "$SRC/platform.dump" | docker compose exec -T platform-db pg_restore -U "${PLATFORM_DB_MIGRATION_USER:-lotediretor}" -d "$PDB" --no-owner --no-acl
cat "$SRC/control.dump" | docker compose exec -T control-db pg_restore -U "${CONTROL_DB_USER:-lotediretor_control}" -d "$CDB" --no-owner --no-acl
docker compose exec -T platform-db psql -v ON_ERROR_STOP=1 -U "${PLATFORM_DB_MIGRATION_USER:-lotediretor}" -d "$PDB" -c "select count(*) from public.schema_migrations" >/dev/null
docker compose exec -T control-db psql -v ON_ERROR_STOP=1 -U "${CONTROL_DB_USER:-lotediretor_control}" -d "$CDB" -c "select count(*) from public.schema_migrations" >/dev/null
echo "Restore drill PASS: database dumps restored into temporary databases."
