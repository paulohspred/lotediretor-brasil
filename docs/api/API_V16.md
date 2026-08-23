# API v16 — Report Engine / Ficha 360

Novos contratos principais:

- `POST /api/v1/property360/properties/from-analysis`
- `GET /api/v1/property360/properties/{id}/ficha`
- `POST /api/v1/property360/properties/{id}/notes`
- `GET /api/v1/property360/properties/{id}/notes`
- `POST /api/v1/property360/diligences`
- `GET /api/v1/property360/diligences`
- `GET /api/v1/reports/{id}/manifest`
- `GET /api/v1/reports/{id}/sections`
- `POST /api/v1/reports/{id}/share`
- `POST /api/v1/reports/{id}/share/{shareId}/revoke`
- `GET /api/v1/municipality-labs/{ibge}/validation-cases`
- `POST /api/v1/municipality-labs/{ibge}/validation-cases`
- `POST /api/v1/municipality-labs/{ibge}/validation-cases/{caseId}/review`

GraphQL adiciona `propertyFichaSummary` e `reports`.
