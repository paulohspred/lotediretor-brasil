#!/usr/bin/env bash
set -euo pipefail

: "${CANARY_BASE_URL:?CANARY_BASE_URL is required}"
: "${CANARY_INTERNAL_API_TOKEN:?CANARY_INTERNAL_API_TOKEN is required}"

BASE_URL="$CANARY_BASE_URL" bash ./ops/runtime/smoke.sh
CANARY_BASE_URL="$CANARY_BASE_URL" CANARY_INTERNAL_API_TOKEN="$CANARY_INTERNAL_API_TOKEN" bash ./ops/release/canary-ai-eval.sh
BASE_URL="$CANARY_BASE_URL" LOAD_PROFILE="${CANARY_LOAD_PROFILE:-ci}" bash ./ops/load/run.sh

echo 'Canary pre-promotion health + AI eval + load gate PASS'
