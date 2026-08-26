# LoteDiretor Brasil — Blueprint v2.0 × implementação atual

Data-base da auditoria: 2026-08-26.

Este documento usa o **Blueprint Final v2.0** como especificação mestre e separa quatro estados: **implementado**, **testado**, **integrado** e **homologado**. Existência de tabela, rota, solver, workflow ou fixture não equivale a homologação.

Baseline runtime validado: `42ac9a13ccb726f68e48a62be75e7d5bec1ffaa7` (`develop`, merge do PR #66), com `ci` #456 PASS e `runtime-e2e` #60 PASS.

## Resumo executivo

O repositório já contém a maior parte da fundação e dos engines centrais previstos no Blueprint: monorepo, APIs/apps/workers, PostgreSQL/PostGIS, object storage, Source Registry/snapshots/provenance, Parcel Resolver, núcleo legal/territorial, Imóvel 360 e RE Rural, Condomínio, Solar, A.I TEC, AI Knowledge Plane, Prefeitura/B2G, Admin Control Plane e Municipality Factory.

Desde a matriz de 23/08 foram implementados incrementos importantes que tornam incorreto continuar classificando A.I TEC avançado, Prefeitura, Admin ou Municipality Factory como frentes “a criar”. O trabalho restante concentra-se em três classes: **(1) UX/browser e gates operacionais de produção implementáveis por código; (2) dados/providers oficiais/licenciados e ambientes reais; (3) revisão/homologação profissional ou institucional**.

`productionHomologated = false` permanece correto.

## Matriz por etapa do Blueprint

| Etapa Blueprint | Estado atual | Já existe | Falta para fechar |
|---|---|---|---|
| 0 — Fundação | **Avançado / runtime local provado / produção não homologada** | monorepo, CI, `npm ci`, build/typecheck, Compose, Keycloak, Caddy, PostGIS, MinIO, Valkey/NATS, OpenSearch, observabilidade configurada, backup/restore drill | staging equivalente, IaC/cloud IAM, secrets/DNS/TLS reais, SLO/alerts/runbooks comprovados, canary, PITR/HA/DR com RPO/RTO |
| 1 — Core territorial | **Avançado / real-source parcial** | Source Registry, snapshots, coverage, geo layers/features, Parcel Resolver, MVT, artigos/relações/conflitos, evaluator temporal, fórmulas/instrumentos e golden corpus v20 | fontes municipais reais em profundidade, cobertura de instrumentos/exceções restantes, golden rules reais e revisão profissional |
| 2 — UX cliente | **Parcial** | site/client/admin, shell e páginas para módulos principais | browser E2E, mobile/a11y, UX final de jornadas, estados de falha/loading/empty, integração real dos fluxos de ponta a ponta |
| 3 — Imóvel 360 | **Código-base avançado / dados e UX parciais** | property/development/report foundations, Ficha 360, mercado v20, notas/diligências e integração territorial/rural | comparáveis reais/licenciados, AVM calibrado/versionado, CRM/prospecção completos, VSO/estoque/absorção, bulk/B2B e browser E2E |
| 4 — RE Rural | **Código operacional / fontes reais parciais** | asset/registry/identity/geometry/overlap/monitor/export, readiness v20, catálogo e adapters existentes | ingestões/homologações reais CAR/SIGEF/SNCR/CCIR/CAFIR-CIB/IBAMA/INPE/FUNAI/CNUC/quilombolas/assentamentos/SICOR, identity graph validado e golden cases profissionais |
| 5 — AI Core | **Fundação forte + runtime local provado** | Knowledge Plane, bitemporalidade, ACL, lexical/hybrid RRF, reranker, registries, router/fallback/circuit breaker, cache, index lifecycle, evals/red-team, OpenSearch runtime | provider externo real, embeddings/chat quality-cost-fallback evaluation, operational red-team/prompt-injection e métricas de qualidade em produção |
| 6 — Condomínio | **Código operacional / produto e real-data parciais** | governança v20, modelo documental, candidates/review, lifecycle, tenant guards e relatórios/integrations foundations | documentos reais variados, parser/layout/OCR em produção, assembleia/e-voting/obras/sanções/manutenção conforme escopo final, monitor legal e browser E2E |
| 7 — Solar | **Engine v20 implementado parcialmente contra o Blueprint completo** | cenário determinístico, layout/electrical foundations, string/MPPT e APIs/runtime de serviço | imagery/DSM/DEM, roof/obstacles/3D, shadows/irradiance calibradas, catálogo/equipamentos, tarifa/OCR/Lei 14.300, BDGD/grid, estrutura/ground-mount e validação profissional |
| 8 — A.I TEC | **Engine avançado / runtime provado** | Site Solver, ingestão, terrain/TIN, road engineering, parking/subsolo, Building/Unit/Room Solver, environment, finance, optimization/Pareto, analyses e exports | datasets reais, qualidade geométrica profissional, Design DNA em profundidade final, IFC/DWG/BIM/licenças reais, UX canvas final e golden sites profissionais |
| 9 — Prefeitura | **Código operacional v20 / homologação institucional pendente** | onboarding, RBAC, datasets municipais, CTM/CIB-SINTER/PGV/IPTU/ITBI/licenciamento, publication/rollback, open-data guard, affected recalculation, materialized export/offboarding, AI institutional ACL | conexões/homologação reais com municípios, Receita/SINTER/CIB, fiscal/licenciamento e dados publicados; operação institucional e browser E2E |
| 10 — Admin SaaS | **Código operacional avançado / providers e produção pendentes** | tenant lifecycle, billing/ledger/dunning/refund/chargeback, contracts/add-ons/coupons, fiscal orchestration, support sessions, CMS, analytics/cohorts, AI Ops, rollout/release/rollback e RLS | Mercado Pago/NFS-e em ambiente real, operação de suporte/CS completa em UI, métricas produtivas, approval/release em staging/prod e browser E2E |
| 11 — Escala nacional | **Municipality Factory implementada localmente** | connector contracts WFS/WMS/ArcGIS/CKAN/HTML/PDF/ZIP, safe discovery, snapshots/provenance, GIS/legal QA, candidate rules, golden lifecycle, publication preparation, change monitoring e coverage snapshots; runtime guards PASS #60 | packs/fontes oficiais reais por município, contratos/licenças, goldens profissionais, métricas nacionais alimentadas por produção e enterprise HA/DR |

## Lacunas transversais obrigatórias da Definition of Done

1. Browser E2E das jornadas críticas, comportamento mobile e acessibilidade.
2. Segurança operacional: pentest independente, prompt-injection/authorization/tenant-leakage em ambiente alvo e correção de achados.
3. Carga, soak e capacidade por serviço/queue com thresholds medidos, não apenas health smoke.
4. Métricas, traces, logs, freshness, alertas, SLOs, owners e runbooks comprovados em ambiente alvo.
5. Staging equivalente à produção, Infrastructure as Code, secrets/IAM/DNS/TLS reais e containers promovidos de forma reproduzível.
6. Canary/rollback executados com evidência, incluindo migrations e AI evals.
7. Backup/restore/PITR e HA/DR de produção com RPO/RTO medidos; o drill local #60 é necessário mas não suficiente.
8. LGPD operacional: classificação, retenção, exclusão/export, auditoria e evidência de execução.
9. Fontes/licenças/provenance reais para qualquer dataset promovido; ausência de snapshot continua `NOT_AVAILABLE`, nunca resposta negativa inventada.
10. Revisão profissional jurídica/engenharia/arquitetura/fiscal onde a conclusão técnica exigir.
11. Branch protection de `main` (#21), observada como `protected=false` em 2026-08-26.

## Evidência crítica recente

O runtime-e2e #60 fecha a falha observada no runtime #58. A causa era uma race entre o `PUT` no OpenSearch e o refresh do índice: o worker marcava `indexed_at` antes de o documento estar pesquisável. O ai-ingest agora usa `refresh=wait_for` antes de marcar o registro como indexado.

O artefato #60 comprova:

- documento privado do tenant A recuperado;
- documento privado do tenant B não recuperado pelo tenant A;
- documento público municipal recuperado somente com escopo público explícito;
- documento com `valid_from=2099` excluído para `baseDate=2026-08-23`;
- OpenSearch single-node saudável para o gate (`yellow`, primárias ativas);
- Municipality Factory guards/RLS, A.I TEC runtime e backup/restore também verdes.

## Caminho crítico atualizado

1. Tratar o issue #13 como próxima frente de código: browser/mobile/a11y, segurança automatizável, performance/capacity, observabilidade/SLO/runbooks, staging/IaC, canary/rollback e LGPD operacional.
2. Em paralelo, executar São Paulo live + golden lots e as demais fontes oficiais/licenciadas sem converter fixtures em verdade municipal.
3. Executar providers externos de IA e avaliações de qualidade/custo/fallback com credenciais reais.
4. Executar revisão profissional/legal/engenharia/arquitetura/fiscal e homologações institucionais aplicáveis.
5. Medir HA/DR/RPO/RTO em ambiente production-like.
6. Proteger `main`, estabilizar release candidate e somente então promover produção e alterar `productionHomologated`.

## Regra de aceite

O objetivo não é maximizar porcentagem de arquivos implementados. O Blueprint considera concluído apenas o que possui os gates aplicáveis de implementação, teste, integração, dados/provenance e operação/homologação. Nenhum contrato simulado, fixture ou status manual substitui evidência real quando o requisito é externo/profissional.
