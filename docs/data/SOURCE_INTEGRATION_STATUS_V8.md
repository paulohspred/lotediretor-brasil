# Source integration status — v8

The v8 data platform separates **verified source discovery** from **published snapshots**. A source is never marked present merely because an endpoint exists.

| Source | v8 software state | Production data state |
|---|---|---|
| IBGE Localidades | adapter + immutable raw + SHA-256 + quality gate + publication/rollback | executable when network is available |
| CAR | generic GeoJSON/WFS/ArcGIS adapter available | endpoint/license still must be selected and verified |
| SIGEF | official Conecta API identified | requires Conecta onboarding, access credentials and firewall/network authorization; dedicated domain mapping still pending |
| IBAMA Embargos | official open-data polygon dataset identified (SHP-ZIP) | SHP-ZIP import adapter still pending; no fake GeoJSON URL is enabled |
| PRODES | official TerraBrasilis WFS family identified and generic WFS paging implemented | exact layer/typeName and data contract must be selected/versioned before ingest |

## Publication rule

`DISCOVERED → CONFIGURED → RAW_CAPTURED → VALIDATED → PUBLISHED`.

Only `PUBLISHED` snapshots may feed technical conclusions. Blocking quality failures produce `REJECTED`; a previous active snapshot remains available for rollback.
