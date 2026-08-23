#!/usr/bin/env bash
set -euo pipefail
timeout="${1:-240}"; start=$(date +%s)
while true; do
  bad=$(docker compose ps --format json | python3 -c 'import json,sys; rows=[]
for l in sys.stdin:
 l=l.strip()
 if l: rows.append(json.loads(l))
b=[]
for r in rows:
 s=(r.get("Service") or r.get("Name") or "");state=(r.get("State") or "").lower();health=(r.get("Health") or "").lower()
 if s in {"minio-init","platform-db-role-init"}: continue
 if state and state!="running": b.append((s,state,health))
 if health and health!="healthy": b.append((s,state,health))
print(len(b))')
  [[ "$bad" == "0" ]] && { echo 'All runtime services healthy'; exit 0; }
  (( $(date +%s)-start > timeout )) && { docker compose ps; echo 'Timeout waiting for healthy services' >&2; exit 1; }
  sleep 5
done
