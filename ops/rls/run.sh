#!/usr/bin/env bash
set -euo pipefail
cat ops/rls/tenant-isolation.sql | docker compose exec -T platform-db psql -v ON_ERROR_STOP=1 -U "${PLATFORM_DB_MIGRATION_USER:-lotediretor}" -d "${PLATFORM_DB_NAME:-lotediretor}"
