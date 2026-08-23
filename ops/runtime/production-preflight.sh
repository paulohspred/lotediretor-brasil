#!/usr/bin/env bash
set -euo pipefail
required=(PUBLIC_DOMAIN AUTH_DOMAIN ACME_EMAIL KEYCLOAK_ADMIN KEYCLOAK_ADMIN_PASSWORD INTERNAL_API_TOKEN OIDC_CLIENT_SECRET PLATFORM_DB_MIGRATION_PASSWORD PLATFORM_DB_APP_PASSWORD PLATFORM_DB_TILES_PASSWORD PLATFORM_DB_EVENT_PASSWORD PLATFORM_DB_WORKER_PASSWORD CONTROL_DB_MIGRATION_PASSWORD CONTROL_DB_APP_PASSWORD CONTROL_DB_WORKER_PASSWORD S3_SECRET_KEY)
failed=0
for k in "${required[@]}"; do
  v="${!k:-}"
  if [[ -z "$v" || "$v" == *change-me* || "$v" == *local* || "$v" == *.invalid ]]; then echo "FAIL $k is missing/default";failed=1; else echo "PASS $k"; fi
done
[[ "${SESSION_COOKIE_SECURE:-true}" == "true" ]] || { echo 'FAIL SESSION_COOKIE_SECURE'; failed=1; }
[[ "${ALLOW_LOCAL_AUTO_MEMBERSHIP:-false}" == "false" ]] || { echo 'FAIL ALLOW_LOCAL_AUTO_MEMBERSHIP'; failed=1; }
exit "$failed"
