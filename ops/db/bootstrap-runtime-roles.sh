#!/usr/bin/env bash
set -euo pipefail
: "${PLATFORM_DB_MIGRATION_USER:?}" "${PLATFORM_DB_MIGRATION_PASSWORD:?}" "${PLATFORM_DB_NAME:?}" "${PLATFORM_DB_APP_PASSWORD:?}" "${PLATFORM_DB_TILES_PASSWORD:?}" "${PLATFORM_DB_EVENT_PASSWORD:?}" "${PLATFORM_DB_WORKER_PASSWORD:?}"
: "${CONTROL_DB_MIGRATION_USER:?}" "${CONTROL_DB_MIGRATION_PASSWORD:?}" "${CONTROL_DB_NAME:?}" "${CONTROL_DB_APP_PASSWORD:?}" "${CONTROL_DB_WORKER_PASSWORD:?}"
export PGPASSWORD="$PLATFORM_DB_MIGRATION_PASSWORD"
psql -v ON_ERROR_STOP=1 -h platform-db -U "$PLATFORM_DB_MIGRATION_USER" -d "$PLATFORM_DB_NAME" \
  --set=app_password="$PLATFORM_DB_APP_PASSWORD" --set=tiles_password="$PLATFORM_DB_TILES_PASSWORD" --set=event_password="$PLATFORM_DB_EVENT_PASSWORD" --set=worker_password="$PLATFORM_DB_WORKER_PASSWORD" <<'SQL'
ALTER ROLE lotediretor_app LOGIN PASSWORD :'app_password';
ALTER ROLE lotediretor_tiles LOGIN PASSWORD :'tiles_password';
ALTER ROLE lotediretor_event_dispatcher LOGIN PASSWORD :'event_password';
ALTER ROLE lotediretor_worker LOGIN PASSWORD :'worker_password';
SQL
export PGPASSWORD="$CONTROL_DB_MIGRATION_PASSWORD"
psql -v ON_ERROR_STOP=1 -h control-db -U "$CONTROL_DB_MIGRATION_USER" -d "$CONTROL_DB_NAME" \
  --set=app_password="$CONTROL_DB_APP_PASSWORD" --set=worker_password="$CONTROL_DB_WORKER_PASSWORD" <<'SQL'
ALTER ROLE lotediretor_control_app LOGIN PASSWORD :'app_password';
ALTER ROLE lotediretor_control_worker LOGIN PASSWORD :'worker_password';
SQL
