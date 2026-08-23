# Production source policy — v11

A source counts as production coverage only when authority and access/license terms are catalogued; exact endpoint/resource/layer contract is pinned; raw bytes are saved immutably with SHA-256; blocking quality checks pass; a snapshot is published atomically; rollback remains possible.

- IBGE municipality adapter is active code.
- SIGEF cannot be declared operational without Conecta onboarding/credentials.
- IBAMA embargo polygons use the official CKAN package and SHP-ZIP conversion path; activation is explicit.
- PRODES uses TerraBrasilis WFS only after an exact current `typeName` is pinned and preflighted.
- CAR is not silently sourced from third-party mirrors.
