#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACT_DIR="${RELEASE_ARTIFACT_DIR:-$ROOT_DIR/runtime-artifacts/release}"
COSIGN_IMAGE="${COSIGN_IMAGE:-ghcr.io/sigstore/cosign/cosign:v3.1.3}"
PROVENANCE_TYPE="${COSIGN_PROVENANCE_TYPE:-slsaprovenance1}"
PULL="${COSIGN_PULL:-0}"
mkdir -p "$ARTIFACT_DIR"

IMAGE_VARS=(
  PLATFORM_API_IMAGE CONTROL_API_IMAGE AI_GATEWAY_IMAGE SOLAR_ENGINE_IMAGE AITEC_ENGINE_IMAGE AITEC_WORKER_IMAGE
  EVENT_DISPATCHER_IMAGE GEO_WORKER_IMAGE DOCUMENT_WORKER_IMAGE REPORT_WORKER_IMAGE RURAL_MONITOR_WORKER_IMAGE
  RURAL_EXPORT_WORKER_IMAGE BILLING_WORKER_IMAGE DATA_PIPELINES_IMAGE AI_INGEST_IMAGE SITE_WEB_IMAGE CLIENT_WEB_IMAGE ADMIN_WEB_IMAGE
)

is_digest_ref(){ [[ "$1" =~ ^[^[:space:]]+@sha256:[0-9a-fA-F]{64}$ ]]; }

if [[ "${1:-}" == "--self-test" ]]; then
  [[ "${#IMAGE_VARS[@]}" -eq 18 ]] || { echo "expected 18 unique release image variables" >&2; exit 1; }
  is_digest_ref 'ghcr.io/example/service@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
  ! is_digest_ref 'ghcr.io/example/service:latest'
  ! is_digest_ref 'ghcr.io/example/service@sha256:abc'
  grep -q 'v3.1.3' <<<"$COSIGN_IMAGE"
  case "$PROVENANCE_TYPE" in slsaprovenance|slsaprovenance02|slsaprovenance1) ;; *) echo "unsupported SLSA provenance type: $PROVENANCE_TYPE" >&2; exit 1;; esac
  echo 'Cosign release signature/provenance contract self-test PASS'
  exit 0
fi

refs=()
for var in "${IMAGE_VARS[@]}"; do
  value="${!var:-}"
  [[ -n "$value" ]] || { echo "$var is required for signed release verification" >&2; exit 1; }
  is_digest_ref "$value" || { echo "$var must be immutable image@sha256: $value" >&2; exit 1; }
  refs+=("$value")
done

# De-duplicate exact refs while preserving order. Every release image variable is
# still required, but aliases to the same immutable artifact need one verification.
mapfile -t unique_refs < <(printf '%s\n' "${refs[@]}" | awk '!seen[$0]++')

key="${COSIGN_PUBLIC_KEY:-}"
identity="${COSIGN_CERTIFICATE_IDENTITY:-}"
issuer="${COSIGN_CERTIFICATE_OIDC_ISSUER:-}"
if [[ -n "$key" && ( -n "$identity" || -n "$issuer" ) ]]; then
  echo 'configure either COSIGN_PUBLIC_KEY or keyless certificate identity/issuer, not both' >&2
  exit 1
fi
if [[ -z "$key" ]]; then
  [[ -n "$identity" && -n "$issuer" ]] || {
    echo 'signed release verification requires COSIGN_PUBLIC_KEY or both COSIGN_CERTIFICATE_IDENTITY and COSIGN_CERTIFICATE_OIDC_ISSUER' >&2
    exit 1
  }
fi

if ! docker image inspect "$COSIGN_IMAGE" >/dev/null 2>&1; then
  if [[ "$PULL" == "1" ]]; then docker pull "$COSIGN_IMAGE"; else
    echo "Cosign image not available locally: $COSIGN_IMAGE (set COSIGN_PULL=1 for explicit pull)" >&2
    exit 2
  fi
fi

common=(--output json)
mounts=()
if [[ -n "$key" ]]; then
  if [[ "$key" != *://* && "$key" != env://* && "$key" != hashivault://* && "$key" != awskms://* && "$key" != gcpkms://* && "$key" != azurekms://* && "$key" != gitlab://* ]]; then
    if [[ "$key" = /* ]]; then
      key_abs="$key"
    else
      key_abs="$ROOT_DIR/$key"
    fi
    [[ -f "$key_abs" ]] || { echo "COSIGN_PUBLIC_KEY file not found: $key_abs" >&2; exit 1; }
    mounts=(-v "$key_abs:/verification/cosign.pub:ro")
    common+=(--key /verification/cosign.pub)
  else
    common+=(--key "$key")
  fi
else
  common+=(--certificate-identity "$identity" --certificate-oidc-issuer "$issuer")
fi

run_cosign(){
  docker run --rm "${mounts[@]}" "$COSIGN_IMAGE" "$@"
}

summary="$ARTIFACT_DIR/signature-provenance.tsv"
printf 'image\tsignature\tprovenance\n' > "$summary"
for ref in "${unique_refs[@]}"; do
  safe=$(printf '%s' "$ref" | sed -E 's#[^A-Za-z0-9_.-]+#_#g')
  sig="$ARTIFACT_DIR/cosign-signature-${safe}.json"
  att="$ARTIFACT_DIR/cosign-provenance-${safe}.json"
  echo "verify signature: $ref"
  run_cosign verify "${common[@]}" "$ref" > "$sig"
  test -s "$sig"
  echo "verify SLSA provenance ($PROVENANCE_TYPE): $ref"
  run_cosign verify-attestation "${common[@]}" --type "$PROVENANCE_TYPE" "$ref" > "$att"
  test -s "$att"
  printf '%s\tPASS\tPASS\n' "$ref" >> "$summary"
done

python3 - "$ARTIFACT_DIR/signature-provenance.json" "$COSIGN_IMAGE" "$PROVENANCE_TYPE" "$summary" <<'PY'
import json,sys,datetime
from pathlib import Path
rows=[]
for line in Path(sys.argv[4]).read_text().splitlines()[1:]:
    if not line.strip(): continue
    image,signature,provenance=line.split('\t')[:3]
    rows.append({'image':image,'signature':signature,'provenance':provenance})
if not rows or not all(x['signature']=='PASS' and x['provenance']=='PASS' for x in rows):
    raise SystemExit('signature/provenance verification incomplete')
json.dump({
  'status':'PASS',
  'cosignImage':sys.argv[2],
  'provenanceType':sys.argv[3],
  'verifiedImages':rows,
  'classification':'REGISTRY_SIGNATURE_AND_SLSA_PROVENANCE_VERIFIED',
  'timestampUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
},open(sys.argv[1],'w'),indent=2)
PY
cat "$ARTIFACT_DIR/signature-provenance.json"
echo 'Release signature + SLSA provenance verification PASS'
