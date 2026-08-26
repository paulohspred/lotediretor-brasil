#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACT_DIR="${SECURITY_ARTIFACT_DIR:-$ROOT_DIR/runtime-artifacts/security}"
TRIVY_IMAGE="${TRIVY_IMAGE:-aquasec/trivy:0.73.0}"
TRIVY_CACHE_DIR="${TRIVY_CACHE_DIR:-$ROOT_DIR/.cache/trivy}"
SCAN_IMAGES="${TRIVY_SCAN_IMAGES:-0}"
PULL="${TRIVY_PULL:-0}"
mkdir -p "$ARTIFACT_DIR" "$TRIVY_CACHE_DIR"

if ! docker image inspect "$TRIVY_IMAGE" >/dev/null 2>&1; then
  if [[ "$PULL" == "1" ]]; then
    docker pull "$TRIVY_IMAGE"
  else
    echo "Trivy image not available locally: $TRIVY_IMAGE" >&2
    echo "Set TRIVY_PULL=1 for an explicit pull." >&2
    exit 2
  fi
fi

run_trivy(){
  docker run --rm \
    -v "$ROOT_DIR:/workspace:ro" \
    -v "$ARTIFACT_DIR:/artifacts" \
    -v "$TRIVY_CACHE_DIR:/root/.cache/trivy" \
    -v /var/run/docker.sock:/var/run/docker.sock \
    "$TRIVY_IMAGE" "$@"
}

echo "==> Trivy filesystem vulnerability/misconfiguration/secret scan"
run_trivy fs \
  --scanners vuln,misconfig,secret \
  --severity HIGH,CRITICAL \
  --ignore-unfixed \
  --exit-code 1 \
  --format json \
  --output /artifacts/trivy-fs.json \
  /workspace

# Produce an all-severity machine-readable inventory as evidence even though only
# HIGH/CRITICAL findings block this pre-Cortex gate.
run_trivy fs \
  --scanners vuln,misconfig,secret \
  --severity UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL \
  --ignore-unfixed \
  --exit-code 0 \
  --format json \
  --output /artifacts/trivy-fs-all.json \
  /workspace

if [[ "$SCAN_IMAGES" == "1" ]]; then
  echo "==> Trivy locally built application images"
  mapfile -t images < <(docker compose images --format json 2>/dev/null | python3 -c '
import json,sys
raw=sys.stdin.read().strip()
items=[]
if raw:
    try:
        parsed=json.loads(raw)
        items=parsed if isinstance(parsed,list) else [parsed] if isinstance(parsed,dict) else []
    except Exception:
        for line in raw.splitlines():
            try:
                value=json.loads(line)
            except Exception:
                continue
            if isinstance(value,list): items.extend(x for x in value if isinstance(x,dict))
            elif isinstance(value,dict): items.append(value)
seen=set()
for x in items:
    repo=str(x.get("Repository") or x.get("repository") or "").strip()
    tag=str(x.get("Tag") or x.get("tag") or "").strip()
    image=str(x.get("Image") or x.get("image") or x.get("ID") or x.get("id") or "").strip()
    ref=(repo+(":"+tag if tag and tag!="<none>" else "")) if repo and repo!="<none>" else image
    if ref and ref!="<none>" and ref not in seen:
        seen.add(ref);print(ref)
')
  if [[ "${#images[@]}" -eq 0 ]]; then
    echo 'TRIVY_SCAN_IMAGES=1 but no Compose images were discovered' >&2
    exit 1
  fi
  : > "$ARTIFACT_DIR/trivy-images.tsv"
  for image in "${images[@]}"; do
    safe=$(printf '%s' "$image" | sed -E 's#[^A-Za-z0-9_.-]+#_#g')
    echo "scan $image"
    if docker run --rm \
      -v "$ARTIFACT_DIR:/artifacts" \
      -v "$TRIVY_CACHE_DIR:/root/.cache/trivy" \
      -v /var/run/docker.sock:/var/run/docker.sock \
      "$TRIVY_IMAGE" image \
      --scanners vuln,secret \
      --severity HIGH,CRITICAL \
      --ignore-unfixed \
      --exit-code 1 \
      --format json \
      --output "/artifacts/trivy-image-${safe}.json" \
      "$image"; then
      printf '%s\tPASS\n' "$image" >> "$ARTIFACT_DIR/trivy-images.tsv"
    else
      printf '%s\tFAIL\n' "$image" >> "$ARTIFACT_DIR/trivy-images.tsv"
      exit 1
    fi
  done
fi

python3 - "$ARTIFACT_DIR/trivy-result.json" "$TRIVY_IMAGE" "$SCAN_IMAGES" <<'PY'
import json,sys,datetime
json.dump({
  'status':'PASS',
  'scanner':'Trivy',
  'image':sys.argv[2],
  'filesystemHighCritical':'PASS',
  'localImagesScanned':sys.argv[3]=='1',
  'classification':'AUTOMATED_VULNERABILITY_SCAN_NOT_INDEPENDENT_PENTEST',
  'timestampUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
},open(sys.argv[1],'w'),indent=2)
PY
cat "$ARTIFACT_DIR/trivy-result.json"
