#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:${HTTP_PORT:-8080}}"
ARTIFACT_DIR="${SECURITY_ARTIFACT_DIR:-runtime-artifacts/security}"
mkdir -p "$ARTIFACT_DIR"
: "${INTERNAL_API_TOKEN:?INTERNAL_API_TOKEN is required}"

request_code(){
  local method="$1" url="$2";shift 2
  curl -sS --max-time 15 -o "$ARTIFACT_DIR/body.tmp" -w '%{http_code}' -X "$method" "$@" "$url" || true
}

# Security and correlation headers must survive the edge proxy.
curl -fsS --max-time 15 -D "$ARTIFACT_DIR/health.headers" -o "$ARTIFACT_DIR/health.json" "$BASE_URL/api/v1/health"
python3 - "$ARTIFACT_DIR/health.headers" <<'PY'
import sys
raw=open(sys.argv[1],encoding='utf-8',errors='replace').read().lower()
required={
 'x-content-type-options':'nosniff',
 'referrer-policy':'strict-origin-when-cross-origin',
 'x-request-id':None,
 'x-trace-id':None,
 'traceparent':None,
}
for name,value in required.items():
    lines=[x for x in raw.splitlines() if x.startswith(name+':')]
    if not lines: raise SystemExit(f'missing security/correlation header: {name}')
    if value and value not in lines[-1]: raise SystemExit(f'bad {name}: {lines[-1]}')
PY

# returnTo must be constrained to local application/admin paths. External URLs
# are normalized to /app/dashboard before being placed in the HttpOnly cookie.
curl -sS --max-time 15 -D "$ARTIFACT_DIR/oidc-start.headers" -o /dev/null \
  "$BASE_URL/api/v1/auth/start?returnTo=https%3A%2F%2Fevil.example%2Fsteal"
python3 - "$ARTIFACT_DIR/oidc-start.headers" <<'PY'
import sys,urllib.parse
lines=open(sys.argv[1],encoding='utf-8',errors='replace').read().splitlines()
cookies=[x.split(':',1)[1].strip() for x in lines if x.lower().startswith('set-cookie:')]
if not cookies: raise SystemExit('OIDC start did not set cookies')
state=next((x for x in cookies if x.startswith('ld_oidc_state=')),None)
verifier=next((x for x in cookies if x.startswith('ld_oidc_verifier=')),None)
ret=next((x for x in cookies if x.startswith('ld_return_to=')),None)
for name,value in [('state',state),('verifier',verifier),('returnTo',ret)]:
    if not value: raise SystemExit(f'missing OIDC {name} cookie')
    low=value.lower()
    if 'httponly' not in low or 'samesite=lax' not in low: raise SystemExit(f'unsafe OIDC {name} cookie: {value}')
encoded=ret.split('=',1)[1].split(';',1)[0]
value=urllib.parse.unquote(encoded)
if value!='/app/dashboard': raise SystemExit(f'open redirect was not sanitized: {value!r}')
PY

# No valid session means no authenticated identity/data surface.
code=$(curl -sS --max-time 15 -o "$ARTIFACT_DIR/fake-session.json" -w '%{http_code}' -H 'Cookie: ld_session=definitely-invalid-session' "$BASE_URL/api/v1/auth/me" || true)
[[ "$code" == "401" ]] || { echo "fake session expected 401, got $code" >&2;exit 1; }
code=$(curl -sS --max-time 15 -o "$ARTIFACT_DIR/privacy-unauth.json" -w '%{http_code}' "$BASE_URL/api/v1/privacy/v20/retention-policies" || true)
[[ "$code" == "401" ]] || { echo "privacy endpoint expected 401, got $code" >&2;exit 1; }

# Machine-to-machine AI endpoints remain closed without the internal token and
# with an invalid token, independent of retrieval backend state.
PAYLOAD='{"tenantId":"0198f020-0000-7000-8000-000000000001","query":"security boundary","scope":{"includePublic":false}}'
code=$(curl -sS --max-time 15 -o "$ARTIFACT_DIR/ai-no-token.json" -w '%{http_code}' -H 'content-type: application/json' -d "$PAYLOAD" "$BASE_URL/ai/v1/retrieve" || true)
[[ "$code" == "403" ]] || { echo "AI no-token expected 403, got $code" >&2;exit 1; }
code=$(curl -sS --max-time 15 -o "$ARTIFACT_DIR/ai-bad-token.json" -w '%{http_code}' -H 'content-type: application/json' -H 'x-internal-token: invalid' -d "$PAYLOAD" "$BASE_URL/ai/v1/retrieve" || true)
[[ "$code" == "403" ]] || { echo "AI bad-token expected 403, got $code" >&2;exit 1; }

# The API does not opt into permissive cross-origin reads.
curl -sS --max-time 15 -D "$ARTIFACT_DIR/cors.headers" -o /dev/null -H 'Origin: https://evil.example' "$BASE_URL/api/v1/health"
if grep -Eqi '^access-control-allow-origin:[[:space:]]*(\*|https://evil\.example)[[:space:]]*$' "$ARTIFACT_DIR/cors.headers"; then
  echo 'permissive CORS detected' >&2;exit 1
fi

# TRACE must never be accepted as a successful application method.
code=$(request_code TRACE "$BASE_URL/api/v1/health")
if [[ "$code" =~ ^2 ]]; then echo "TRACE unexpectedly accepted with HTTP $code" >&2;exit 1;fi

python3 - "$ARTIFACT_DIR/result.json" <<'PY'
import json,sys,datetime
json.dump({'status':'PASS','timestampUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':['security_headers','oidc_cookie_flags','open_redirect_sanitization','fake_session_rejected','privacy_unauth_rejected','ai_internal_token_boundary','cors_not_permissive','trace_not_accepted']},open(sys.argv[1],'w'),indent=2)
PY
cat "$ARTIFACT_DIR/result.json"
echo 'Runtime security baseline PASS'
