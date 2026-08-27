#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_URL="${BASE_URL:-http://127.0.0.1:${HTTP_PORT:-8080}}"
LOAD_PROFILE="${LOAD_PROFILE:-ci}"
ARTIFACT_DIR="${LOAD_ARTIFACT_DIR:-$ROOT_DIR/runtime-artifacts/load}"
K6_IMAGE="${K6_IMAGE:-grafana/k6:0.57.0}"

mkdir -p "$ARTIFACT_DIR"

echo "k6 profile=$LOAD_PROFILE base=$BASE_URL image=$K6_IMAGE"

docker run --rm \
  --network host \
  -v "$ROOT_DIR/ops/load:/work:ro" \
  -v "$ARTIFACT_DIR:/artifacts" \
  -e "BASE_URL=$BASE_URL" \
  -e "LOAD_PROFILE=$LOAD_PROFILE" \
  -e "INTERNAL_API_TOKEN=${INTERNAL_API_TOKEN:-}" \
  "$K6_IMAGE" run \
    --summary-export /artifacts/k6-summary.json \
    /work/k6-smoke.js

echo "k6 artifacts: $ARTIFACT_DIR"
