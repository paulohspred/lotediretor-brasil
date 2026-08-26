#!/usr/bin/env bash
set -euo pipefail

./ops/runtime/production-preflight.sh
python3 ops/security/production-parity.py
python3 ops/security/render-keycloak-production.py >/dev/null
python3 ops/release/production-homologation.py --self-test

realm=infra/keycloak/generated/realm-lotediretor.production.json
python3 - "$realm" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]));assert not p.get('users');assert p.get('bruteForceProtected') is True;assert p.get('sslRequired')=='external'
ra={x.get('alias'):x for x in p.get('requiredActions',[])};assert ra.get('CONFIGURE_TOTP',{}).get('defaultAction') is True
c=next(x for x in p['clients'] if x['clientId']=='lotediretor-app');assert '__' not in c.get('secret','');assert c['redirectUris'][0].startswith('https://')
print('Keycloak production realm security PASS')
PY

# Fail if known development credentials/defaults appear literally in the production override.
if grep -Eq 'lotediretor_local|change-me-app|change-me-control-app|change-me-tiles|local-internal-change-me|local-lotediretor-secret' docker-compose.production.yml; then
  echo 'FAIL production compose contains development credential defaults' >&2;exit 1
fi

if [[ "${PRODUCTION_HOMOLOGATED:-false}" == "true" ]]; then
  : "${PRODUCTION_HOMOLOGATION_EVIDENCE:?PRODUCTION_HOMOLOGATION_EVIDENCE is required when PRODUCTION_HOMOLOGATED=true}"
  python3 ops/release/production-homologation.py
else
  echo 'productionHomologated=false (expected until final external evidence is complete)'
fi

echo 'Production security gate PASS'
