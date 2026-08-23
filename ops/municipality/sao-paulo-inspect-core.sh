#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROFILE="$ROOT/data/municipality-labs/sao-paulo-3550308.json"
python "$ROOT/workers/data-pipelines/municipality_lab.py" --profile "$PROFILE" inspect-wfs --source SP_GEOSAMPA_WFS --typename geoportal:lote_cidadao --srs-name EPSG:4326
python "$ROOT/workers/data-pipelines/municipality_lab.py" --profile "$PROFILE" inspect-wfs --source SP_GEOSAMPA_WFS --typename geoportal:perimetro_zona_lei_18177_24 --srs-name EPSG:4326
