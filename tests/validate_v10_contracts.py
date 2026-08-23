from pathlib import Path
import json,sys
R=Path(__file__).resolve().parents[1]
prod=(R/'docker-compose.production.yml').read_text(); caddy=(R/'infra/caddy/Caddyfile.production').read_text()
checks={
 'version_v10':(R/'VERSION').read_text().strip()=='v10',
 'production_compose':(R/'docker-compose.production.yml').exists(),
 'keycloak_not_dev':'command: ["start", "--import-realm"]' in prod and 'start-dev' not in prod,
 'secure_cookie':'SESSION_COOKIE_SECURE: "true"' in prod,
 'local_membership_off':'ALLOW_LOCAL_AUTO_MEMBERSHIP: "false"' in prod,
 'tls_edge':'Strict-Transport-Security' in caddy and '443:443' in prod,
 'preflight':(R/'ops/runtime/production-preflight.sh').exists(),
 'runtime_acceptance':'runtime-isolation.sh' in (R/'ops/runtime/acceptance.sh').read_text() and 'restore-drill.sh' in (R/'ops/runtime/acceptance.sh').read_text(),
}
print(json.dumps(checks,indent=2));bad=[k for k,v in checks.items() if not v]
if bad:print('FAILED',bad,file=sys.stderr);sys.exit(1)
