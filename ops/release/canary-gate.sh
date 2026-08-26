#!/usr/bin/env bash
set -euo pipefail

: "${CANARY_BASE_URL:?CANARY_BASE_URL is required}"

BASE_URL="$CANARY_BASE_URL" bash ./ops/runtime/smoke.sh
BASE_URL="$CANARY_BASE_URL" LOAD_PROFILE="${CANARY_LOAD_PROFILE:-ci}" bash ./ops/load/run.sh

echo 'Canary pre-promotion gate PASS'
