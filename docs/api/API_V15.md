# API v15 — Core Territorial

Novos contratos principais:

- `POST /api/v1/parcel/resolve` — ponto, polígono, endereço indexado ou identificador.
- `GET /api/v1/municipalities/{ibge}/coverage` — disponibilidade versus publicação real.
- `GET /api/v1/legal/search` — busca em artigos/versionamento jurídico.
- `GET /api/v1/legal/rules/effective` — regras `CONFIRMED` vigentes.
- `POST /api/v1/spatial/intersections` — interseções contra layers publicados.
- `GET /api/v1/nearby` — proximidade por raio.
- `POST /api/v1/analysis` — análise temporal/reproduzível, idempotente.
- `GET /api/v1/analysis/{id}/evidence` — parâmetros, relações, cálculos e snapshots.

O `GET /api/v1/parcel/resolve?lat=...&lon=...` permanece por compatibilidade.

GraphQL adiciona `municipalityCoverage` e `effectiveRules`, além das superfícies já existentes.
