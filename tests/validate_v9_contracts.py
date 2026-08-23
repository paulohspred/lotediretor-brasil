from pathlib import Path
import json,sys
R=Path(__file__).resolve().parents[1]
compose=(R/'docker-compose.yml').read_text()
platform=(R/'services/platform-api/src/main.ts').read_text()
controller=(R/'services/platform-api/src/v7.controller.ts').read_text()
checks={
 'version_v9':(R/'VERSION').read_text().strip()=='v9',
 'platform_runtime_non_owner':'PLATFORM_DB_APP_USER:-lotediretor_app' in compose,
 'platform_migration_url':'PLATFORM_MIGRATION_DATABASE_URL' in platform and 'PLATFORM_MIGRATION_DATABASE_URL' in compose,
 'control_runtime_non_owner':'CONTROL_DB_APP_USER:-lotediretor_control_app' in compose,
 'control_migration_url':'CONTROL_MIGRATION_DATABASE_URL' in (R/'services/control-api/src/main.ts').read_text(),
 'tiles_readonly':'PLATFORM_DB_TILES_USER:-lotediretor_tiles' in compose,
 'force_rls':'FORCE ROW LEVEL SECURITY' in (R/'db/platform/migrations/120_v9_runtime_security.sql').read_text(),
 'rls_with_check':'WITH CHECK' in (R/'db/platform/migrations/120_v9_runtime_security.sql').read_text(),
 'runtime_rls_drill':'Runtime non-owner RLS isolation PASS' in (R/'ops/rls/runtime-isolation.sh').read_text(),
 'role_bootstrap':(R/'ops/db/bootstrap-runtime-roles.sh').exists(),
 'aitec_sha_bug_fixed':'Metadata:{sha256:sha,scenario:scenarioId}' in controller and 'Metadata:{sha256,scenario:scenarioId}' not in controller,
}
print(json.dumps(checks,indent=2))
bad=[k for k,v in checks.items() if not v]
if bad: print('FAILED',bad,file=sys.stderr);sys.exit(1)
