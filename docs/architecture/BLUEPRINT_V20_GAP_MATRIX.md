# LoteDiretor Brasil — Blueprint v2.0 × implementação atual

Data-base da auditoria: 2026-08-23.

Este documento usa o **Blueprint Final v2.0** como especificação mestre e separa quatro estados: **implementado**, **testado**, **integrado** e **homologado**. Existência de tabela, rota ou solver não equivale a homologação.

## Resumo executivo

O repositório já contém uma fundação substancial: monorepo, APIs/apps/workers, PostgreSQL/PostGIS, Source Registry, snapshots/provenance, Parcel Resolver, núcleo legal/territorial, Imóvel 360 e relatórios, RE Rural, Condomínio, Solar, A.I TEC, AI Knowledge Plane, Prefeitura/município-lab, Control Plane e observabilidade configurada. A v19-rc.3 também adicionou profundidade relevante em A.I TEC e elétrica Solar.

O produto ainda não está completo contra o Blueprint. As lacunas críticas são: runtime E2E plenamente verde; São Paulo com ingestão completa + QA + golden lots; Rule Engine legal/urbanístico profundo; AI Core em runtime real; dados externos/licenciados; A.I TEC avançado até Unit Solver/BIM; Solar 3D/regulatório/financeiro calibrado; Condomínio operacional completo; Prefeitura/CTM/SINTER; Admin SaaS integral; Municipality Factory; browser E2E, segurança, carga, staging, canary e DR.

## Matriz por etapa do Blueprint

| Etapa Blueprint | Estado atual | Já existe | Falta para fechar |
|---|---|---|---|
| 0 — Fundação | **Avançado / não homologado** | monorepo, CI, `npm ci`, build/typecheck, Compose, Keycloak, Caddy, PostGIS, MinIO, Valkey/NATS, OpenSearch, OTel/Prometheus/Grafana/Tempo configurados | Runtime E2E integral verde, observabilidade comprovada em runtime, staging/prod, IaC, secrets reais, canary/rollback, PITR/DR |
| 1 — Core territorial | **Parcial avançado** | Source Registry, snapshots, coverage, geo layers/features, Parcel Resolver, MVT base, artigos legais, relações, conflitos, cálculos/evidências, município-lab | ingestão nacional robusta, regras urbanísticas completas, hierarquia/efeitos legais completos, fórmulas/tabelas/exceções, golden rules e memória de cálculo abrangente |
| 2 — UX cliente | **Parcial** | site/client/admin apps e shell funcional | browser E2E, mobile/a11y, UX final de todos os módulos, workflows completos e testes de falha |
| 3 — Imóvel 360 | **Parcial** | property/development/report foundations, Ficha 360, notas/diligências, AVM/mercado foundations | dados reais/licenciados, comparáveis, AVM calibrado/versionado, VSO/estoque/absorção, CRM completo, prospecção/composição de lotes e APIs enterprise |
| 4 — RE Rural | **Parcial** | asset/registry/identity/geometry/overlap/monitor/export foundations; fontes nacionais catalogadas | ingestões reais CAR/SIGEF/SNCR/CCIR/CAFIR-CIB/IBAMA/INPE/FUNAI/CNUC/quilombolas/assentamentos, identity graph validado, SICOR e golden cases profissionais |
| 5 — AI Core | **Fundação forte / runtime parcial** | Knowledge Plane, bitemporalidade, evidence/high-risk gates, registry, estrutura hybrid retrieval | OpenSearch/índice vetorial reais, embeddings versionados, RRF/reranker avaliados, ACL antes do retrieval em todos os domínios, router/provider/fallback/circuit breaker, evals/red-team completos |
| 6 — Condomínio | **Parcial** | modelo documental/condomínio, candidatos de regra, relatórios e integração inicial | parser/layout avançado, temporalidade/conflitos completos, assembleia/e-voting, obras/ART-RRT, sanções/defesa, manutenção/compliance, integrações e monitor legal |
| 7 — Solar | **Preliminar avançado na elétrica** | site/layout foundations, relatório, design elétrico string/MPPT com inputs explícitos | imagery/DSM/DEM, roof/obstacles, cena 3D, sombras/irradiância calibradas, catálogo comercial, clipping/perdas/bateria, OCR conta, TE/TUSD/SCEE/Lei 14.300, financeiro, BDGD/grid, ground-mount/tracker e calibração |
| 8 — A.I TEC | **MVP avançado** | Site Solver, parking superfície, acesso/road conceitual, locks/branch, unit mix, cut-fill por amostra, Building Stack, analyses e exports básicos | ingestão CAD/GIS ampla, DEM/TIN real, viário engenharia, garagem/subsolo, Building Solver completo, Unit Solver, Design DNA, performance ambiental, VGV/CAPEX/Pareto, IFC/DWG/BIM e golden sites profissionais |
| 9 — Prefeitura | **Fundação / município-lab** | perfis municipais, publicação por dataset, contratos São Paulo, laboratório/golden plan, RBAC foundations | onboarding municipal, CTM/CIB/SINTER/PGV, IPTU/ITBI/licenciamento, publicação 4-olhos, recálculo afetado, open data, auditoria/export/offboarding e IA institucional completa |
| 10 — Admin SaaS | **Parcial** | Control Plane, tenant/catalog/billing foundations, Mercado Pago foundations, CMS/support/ops/release schemas parciais | assinatura/dunning/refund/chargeback completos, contratos/add-ons/coupons, fiscal/NFS-e, CS/support session, analytics/cohorts, AI Ops, release approvals, incident/backup/DR dashboards |
| 11 — Escala nacional | **Inicial** | Source Registry e padrões reutilizáveis de município/conectores | Municipality Factory, descoberta automática, adaptadores reutilizáveis completos, golden suites por município, métricas de cobertura nacional, enterprise/HA/DR e otimização |

## Lacunas transversais obrigatórias da Definition of Done

1. API/schema versionados e contratos de dados estáveis por módulo.
2. Permissões/entitlements e testes de isolamento por tenant.
3. Provenance/licença obrigatórias para qualquer dataset promovido.
4. Unit + integration + contract + E2E + falhas, não apenas testes estáticos.
5. Métricas, traces, logs, freshness e alertas por módulo.
6. Runbook, rollback, owner, SLO e retenção.
7. Desktop/mobile/a11y e browser E2E.
8. Evidência reproduzível para qualquer conclusão técnica.
9. Security review, pentest, prompt-injection/tenant-leakage e LGPD operacional.
10. Staging equivalente, carga/soak, canary, backup/restore, PITR e DR.

## Caminho crítico adotado

1. Fechar Runtime E2E (#23/#20/#22).
2. Fechar São Paulo ponta a ponta (#3): ingestão paginada/streaming, QA, promoção, legal/rules e golden lots.
3. Completar Core Territorial + Legal/Rule Engine (#4).
4. Colocar AI Core em runtime real (#5/#22).
5. Completar A.I TEC (#6) e Solar (#7) sobre o núcleo confirmado.
6. Completar Imóvel 360/RE Rural (#8) e Condomínio (#9).
7. Completar Prefeitura (#10) e Admin (#11).
8. Municipality Factory (#12).
9. Go-live final (#13).

## Primeira entrega v20 iniciada nesta branch

A migration `197_v20_core_legal_foundation.sql` inicia a expansão do Core/Legal com:

- relações legais temporais e tipadas (`ALTERA`, `REVOGA`, `REGULAMENTA`, `SUSPENDE_EFICACIA` etc.);
- vínculo opcional artigo→artigo;
- metadados de revisão sem auto-homologação;
- identidade/família/efeito/fórmula/schema para regras determinísticas;
- dependências explícitas entre regras (`REQUIRES`, `OVERRIDES`, `LIMITS`, `EXCLUDES`, `DERIVES_FROM`);
- bindings genéricos para parâmetros, usos, instrumentos urbanísticos, gatilhos de licenciamento, restrições espaciais e cálculos;
- estado inicial `CANDIDATE` para impedir confirmação silenciosa.

Próximos incrementos desta frente: evaluator/contexto urbanístico ampliado, resolução de precedência/conflitos, fórmulas determinísticas, instrumentos (outorga/CEPAC/TDC), ZEIS/HIS/HMP, EIV/PGT, patrimônio/aeródromo/servidões/melhoramentos e golden tests.
