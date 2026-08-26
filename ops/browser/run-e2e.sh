#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACT_DIR="${BROWSER_ARTIFACT_DIR:-$ROOT_DIR/runtime-artifacts/browser}"
BASE_URL="${BROWSER_BASE_URL:-http://127.0.0.1:${HTTP_PORT:-8080}}"
IMAGE="${PLAYWRIGHT_IMAGE:-mcr.microsoft.com/playwright:v1.55.0-noble}"
PLAYWRIGHT_VERSION="${PLAYWRIGHT_VERSION:-1.55.0}"
AXE_VERSION="${AXE_PLAYWRIGHT_VERSION:-4.10.2}"

mkdir -p "$ARTIFACT_DIR"

echo "Browser E2E base URL: $BASE_URL"
echo "Playwright image: $IMAGE"

docker run --rm \
  --network host \
  --ipc host \
  -v "$ROOT_DIR/tests/browser:/suite:ro" \
  -v "$ARTIFACT_DIR:/artifacts" \
  -e "BROWSER_BASE_URL=$BASE_URL" \
  -e "PLAYWRIGHT_ARTIFACT_DIR=/artifacts" \
  "$IMAGE" \
  bash -lc "set -euo pipefail
    mkdir -p /work && cd /work
    npm init -y >/dev/null
    npm install --no-save --package-lock=false --no-audit --no-fund @playwright/test@${PLAYWRIGHT_VERSION} @axe-core/playwright@${AXE_VERSION} >/dev/null
    cp /suite/*.mjs /work/
    npx playwright test --config=/work/playwright.config.mjs /work/platform.spec.mjs
  "

echo "Browser E2E artifacts: $ARTIFACT_DIR"
