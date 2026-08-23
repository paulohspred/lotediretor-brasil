# Matriz canônica de versões — LoteDiretor SaaS

Esta linha foi reconstruída cumulativamente a partir da Foundation física v1. Um número só é atribuído quando o código do marco está presente na árvore.

| Versão | Marco implementado no código |
|---|---|
| v1 | Foundation: monorepo, três frontends, autenticação base, bancos, PostGIS, Keycloak, Valkey, MinIO/NATS/Caddy e contratos iniciais. |
| v2 | Núcleo territorial: Source Registry, sincronização IBGE, catálogo municipal, Parcel Resolver temporal, regras CONFIRMED e análise urbanística determinística. |
| v3 | Imóvel 360: dashboard, propriedades, Explorer, comparáveis DEMO explícitos, AVM determinístico e fila de relatório. |
| v4 | RE Rural, Condomínio e Prefeitura: overlaps, monitores, chunks/regras temporais, workspace municipal, CTM/IPTU e RBAC. |
| v5 | Solar, A.I TEC, AI Gateway/traces e Admin Control Plane ampliado. |
| v6 | Integração: MVT Martin restrito ao schema tiles, upload MinIO+SHA-256, OCR/ingestão, PDF worker, pipeline IBGE, Mercado Pago webhook/ledger/entitlements, CMS publicado e frontends conectados. |
| v7 | Marco ~70% de software: data contracts/quality/publication, Imóvel 360 CRM/developments, adaptador geoespacial configurável, search/indexing, Solar financeiro, A.I TEC ranking/export, server-side AI grounding, Admin Ops e hardening transversal. |

## Regra de segurança

Dados ausentes não são convertidos em confirmação. Comparáveis DEMO são marcados como DEMO; parâmetros legais só entram na análise quando `CONFIRMED`; A.I TEC não converte cenário inválido em válido; dados rurais só contam após snapshot real validado.

## Limite de validação neste ambiente

A árvore passa por validação estática de JSON/YAML/Python/TypeScript parser, testes unitários dos cálculos puros e checks de contratos. A execução Docker Compose ponta a ponta deve ser feita em ambiente com Docker; não é declarada como testada aqui.
