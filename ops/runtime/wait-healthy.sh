#!/usr/bin/env bash
set -euo pipefail

timeout="${1:-300}"
start=$(date +%s)

while true; do
  snapshot=/tmp/ld-compose-health.jsonl
  docker compose ps -a --format json > "$snapshot"

  bad=$(python3 - "$snapshot" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text().strip() if path.exists() else ""
if not text:
    print(999)
    raise SystemExit(0)

rows = []
try:
    if text.startswith("["):
        rows = json.loads(text)
    else:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
except Exception:
    print(999)
    raise SystemExit(0)

one_shot = {
    "minio-init",
    "platform-migrate",
    "control-migrate",
    "platform-db-role-init",
}

bad = []
for row in rows:
    service = row.get("Service") or row.get("Name") or "unknown"
    state = str(row.get("State") or "").lower()
    health = str(row.get("Health") or "").lower()
    exit_code = row.get("ExitCode")

    if service in one_shot:
        # Compose one-shot services are healthy when they exited successfully.
        if state in {"exited", "stopped"}:
            try:
                code = int(exit_code or 0)
            except (TypeError, ValueError):
                code = 1
            if code != 0:
                bad.append((service, state, health, code))
        elif state and state != "running":
            bad.append((service, state, health, exit_code))
        continue

    if state != "running":
        bad.append((service, state, health, exit_code))
        continue
    if health and health != "healthy":
        bad.append((service, state, health, exit_code))

print(len(bad))
PY
)

  if [[ "$bad" == "0" ]]; then
    echo 'All runtime services healthy'
    exit 0
  fi

  if (( $(date +%s) - start > timeout )); then
    docker compose ps -a
    echo "Timeout waiting for healthy services ($bad unhealthy)" >&2
    exit 1
  fi

  sleep 5
done
