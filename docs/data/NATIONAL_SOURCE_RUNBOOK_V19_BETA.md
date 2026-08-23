# National source activation — v19-beta

This runbook implements the Blueprint rule that a discovered official endpoint is not equivalent to an ingested, quality-approved dataset.

## IBGE Localidades

The `data-pipelines` worker has a dedicated adapter. It snapshots the raw response, hashes it, validates municipality count/code/UF presence, loads `core.municipality` and only then activates `source.publication`.

## IBAMA embargo polygons

Use the official IBAMA CKAN package for **Termos de Embargo**. Configure the CKAN `package_show` endpoint in `IBAMA_EMBARGO_SOURCE_URL`, set `IBAMA_EMBARGO_SOURCE_ENABLED=true` and provide `IBAMA_EMBARGO_SOURCE_LICENSE_URL`. The adapter selects a SHP/ZIP resource, converts it with GDAL to EPSG:4326, runs geometry/coordinate quality gates and publishes only after PASS.

No third-party mirror is activated as official data.

## PRODES / TerraBrasilis

TerraBrasilis exposes WFS. Do not guess a layer. First run:

```bash
python ops/data/wfs-discover.py --url https://terrabrasilis.dpi.inpe.br/geoserver/ows --pattern 'PRODES|desmat'
```

After operator review, pin the exact typeName in `PRODES_SOURCE_TYPENAME`, set the official WFS URL/license, request `EPSG:4326`, run `ops/data/source-preflight.py`, and only then enable ingestion.

## SIGEF

SIGEF/Conecta is **not** routed through the generic GeoJSON/WFS connector. It requires authorized Conecta credentials and an API-specific adapter/contract. `SIGEF_SOURCE_ENABLED=true` without a credential fails preflight by design.

## Production gate

Every activated source must have: authority, access class, license/terms, immutable raw object, SHA-256, parser version, dataset contract, blocking QA PASS, publication pointer and provenance. A failed coordinate-range check prevents publication because projected coordinates must never be silently stored as EPSG:4326.
