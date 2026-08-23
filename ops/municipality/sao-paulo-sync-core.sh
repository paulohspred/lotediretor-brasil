#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROFILE="$ROOT/data/municipality-labs/sao-paulo-3550308.json"
LICENSE_URL='https://prefeitura.sp.gov.br/web/licenciamento/w/licen%C3%A7a-para-uso-de-dados-do-geosampa'
python "$ROOT/workers/data-pipelines/municipality_lab.py" --profile "$PROFILE" sync-wfs \
  --source SP_GEOSAMPA_WFS --dataset PARCEL --typename geoportal:lote_cidadao \
  --layer-code SP_GEOSAMPA_PARCEL --domain cadastre --license-url "$LICENSE_URL"
python "$ROOT/workers/data-pipelines/municipality_lab.py" --profile "$PROFILE" sync-wfs \
  --source SP_GEOSAMPA_WFS --dataset ZONEAMENTO --typename geoportal:perimetro_zona_lei_18177_24 \
  --layer-code SP_GEOSAMPA_ZONE_18177_2024 --domain planning --license-url "$LICENSE_URL"
