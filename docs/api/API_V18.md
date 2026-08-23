# API v18 — Condomínio e Energia Solar

A v18 mantém `/api/v1` e os contratos transversais de autenticação, tenant/RLS, idempotência e outbox.

## Condomínio

Principais superfícies:

- `GET /api/v1/condominiums/:id/dashboard`
- buildings, units e common-areas
- works + decision
- assemblies + agenda + vote-summary + decisions
- maintenance, occurrences e compliance
- `POST /api/v1/condominiums/:id/report`

Ações de gestão exigem `condo_manager` ou `admin`. Regras extraídas/deliberações não são promovidas automaticamente para `CONFIRMED`.

## Solar

Principais superfícies:

- site/surface/obstacle
- equipment
- `POST /api/v1/solar/projects/:id/layouts/auto`
- `GET /api/v1/solar/projects/:id/scene-3d`
- bills e energy-balance
- sun-path
- scenario compare
- `POST /api/v1/solar/projects/:id/report`

O Solar Engine interno expõe `layout-2d`, `energy-balance` e `sun-path`; acesso é protegido por token interno.
