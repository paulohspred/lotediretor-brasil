#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:${HTTP_PORT:-8080}}"
ARTIFACT_DIR="${SECURITY_ARTIFACT_DIR:-runtime-artifacts/security}"
IMAGE="${ZAP_IMAGE:-ghcr.io/zaproxy/zaproxy:stable}"
mkdir -p "$ARTIFACT_DIR"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  if [[ "${ZAP_PULL:-0}" == "1" ]]; then
    docker pull "$IMAGE"
  else
    echo "ZAP image is not present locally: $IMAGE" >&2
    echo "Pre-pull it or run with ZAP_PULL=1. This optional scanner is intentionally not an internet-dependent CI prerequisite." >&2
    exit 2
  fi
fi

rm -f "$ARTIFACT_DIR/zap-report.json" "$ARTIFACT_DIR/zap-report.html" "$ARTIFACT_DIR/zap-report.md"
set +e
docker run --rm --network host \
  -v "$(cd "$ARTIFACT_DIR" && pwd):/zap/wrk:rw" \
  "$IMAGE" zap-baseline.py \
  -t "$BASE_URL" \
  -m "${ZAP_MINUTES:-3}" \
  -J zap-report.json -r zap-report.html -w zap-report.md -I
zap_exit=$?
set -e

[[ -f "$ARTIFACT_DIR/zap-report.json" ]] || { echo "ZAP did not produce JSON report (exit=$zap_exit)" >&2;exit 1; }
python3 - "$ARTIFACT_DIR/zap-report.json" <<'PY'
import json,sys
raw=json.load(open(sys.argv[1],encoding='utf-8'))
site=raw.get('site') or []
alerts=[]
for s in site:
    alerts.extend(s.get('alerts') or [])
high=[a for a in alerts if str(a.get('riskcode'))=='3' or str(a.get('riskdesc','')).lower().startswith('high')]
medium=[a for a in alerts if str(a.get('riskcode'))=='2' or str(a.get('riskdesc','')).lower().startswith('medium')]
summary={'status':'PASS' if not high else 'FAIL','high':len(high),'medium':len(medium),'total':len(alerts),'highAlerts':[{'name':a.get('name') or a.get('alert'),'instances':len(a.get('instances') or [])} for a in high]}
print(json.dumps(summary,indent=2,ensure_ascii=False))
if high: raise SystemExit('ZAP high-risk alerts block pre-Cortex qualification')
PY

echo "ZAP baseline PASS (scanner exit=$zap_exit; high-risk alerts=0)"
