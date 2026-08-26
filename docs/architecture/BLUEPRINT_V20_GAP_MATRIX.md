# LoteDiretor Brasil — Blueprint v2.0 × implementação atual

Data-base da auditoria: 2026-08-26.

Este documento usa o **Blueprint Final v2.0** como especificação mestre e separa quatro estados: **implementado**, **testado**, **integrado** e **homologado**. Existência de tabela, rota, solver, workflow ou fixture não equivale a homologação.

Baseline de produção anterior validado em `develop`: `42ac9a13ccb726f68e48a62be75e7d5bec1ffaa7`, com CI #456 e runtime-e2e #60 PASS. O PR #68 contém a qualificação v20 pré-Cortex e permanece **não mergeado** até CI/runtime executarem steps reais e ficarem verdes.

`productionHomologated = false` permanece obrigatório.

## Resumo executivo

O repositório contém a fundação e os engines centrais previstos no Blueprint: monorepo, APIs/apps/workers, PostgreSQL/PostGIS, object storage, Source Registry/snapshots/provenance, Parcel Resolver, núcleo legal/territorial, Imóvel 360/RE Rural, Condomínio, Solar, A.I TEC, AI Knowledge Plane, Prefeitura/B2G, Admin Control Plane e Municipality Factory.

O PR #68 fecha grande parte das lacunas que antes eram apenas operacionais: OIDC/browser real, desktop/mobile/a11y, quatro jornadas críticas com UI, carga `ci/soak/capacity`, RED metrics/traces/logs/alerts, fila A.I TEC observável e resiliente, LGPD operacional, fault injection, production/staging parity estrutural, promoção por digest, rollback contract, supply-chain/SBOM, backup/restore DB+object storage e DR sintético local com RPO/RTO.

O trabalho restante concentra-se em: **(1) executar e corrigir integralmente esses gates no Cortex/runner real; (2) dados/providers oficiais/licenciados e ambiente final; (3) acabamento profissional/UX avançada específica de domínio; (4) revisão/homologação profissional ou institucional**.

## Matriz por etapa do Blueprint

| Etapa Blueprint | Estado atual | Já existe | Falta para fechar |
|---|---|---|---|
| 0 — Fundação | **Avançado / qualificação local codificada / produção não homologada** | monorepo, CI, npm lock/typecheck/build, Compose, Keycloak, Caddy, PostGIS, MinIO versionado, Valkey/NATS, OpenSearch, RED/OTLP, Prometheus/Grafana/Loki/Tempo/Alertmanager, SLO/runbooks, SBOM, backup/restore e DR local | execução verde do novo gate, cloud/IaC escolhido, IAM/secrets/DNS/TLS/registry reais, PITR/HA/DR e canary/rollback no ambiente final |
| 1 — Core territorial | **Avançado / real-source parcial** | Source Registry, snapshots, coverage, geo layers/features, Parcel Resolver, MVT, artigos/relações/conflitos, evaluator temporal, fórmulas/instrumentos, analysis/evidence/report e golden corpus v20 | fontes municipais reais em profundidade, instrumentos/exceções restantes, golden rules reais e revisão profissional |
| 2 — UX cliente | **Avançado para jornadas críticas / acabamento amplo pendente** | site/client/admin, shell/workspaces, OIDC real, desktop/mobile, axe WCAG A/AA, estados básicos e UI E2E de análise→relatório, condo upload→chat, billing→entitlement e A.I TEC job | exploração visual/manual ampla, refinamento de estados loading/error/empty em todas as ações e UX profissional/canvas específica dos módulos avançados |
| 3 — Imóvel 360 | **Código e jornada principal avançados / dados reais parciais** | Ficha 360, análise territorial, relatório congelado, notas/diligências, developments, CRM/leads, market snapshots, comparables/AVM contracts e UI análise→relatório | comparáveis reais/licenciados, AVM calibrado/versionado com corpus real, CRM/prospecção de produção, VSO/estoque/absorção reais e bulk/B2B validado |
| 4 — RE Rural | **Código operacional / fontes reais parciais** | asset/registry/identity/geometry/overlap/monitor/export, readiness v20, catálogo/adapters e governance | ingestões/homologações reais CAR/SIGEF/SNCR/CCIR/CAFIR-CIB/IBAMA/INPE/FUNAI/CNUC/quilombolas/assentamentos/SICOR, identity graph validado e goldens profissionais |
| 5 — AI Core | **Fundação forte + runtime local provado** | Knowledge Plane, bitemporalidade, ACL, lexical/hybrid RRF, reranker, registries, router/fallback/circuit breaker, cache, index lifecycle, evals/red-team, OpenSearch isolation e AI Gateway RED/OTLP | provider/embeddings/chat reais, avaliação quality-cost-fallback com credenciais reais, red-team operacional no ambiente alvo e métricas de qualidade de produção |
| 6 — Condomínio | **Código operacional + UI crítica implementada / real-data parcial** | governança v20, documentos privados, ingest/index, rules candidates/review, unidades/áreas/obras/assembleias/manutenção/ocorrências/compliance, A.I Condomínio e UI upload→chat | corpus documental real variado, OCR/layout em produção, fluxos legais/profissionais finais, e-voting/e-signature/provider real quando aplicável e monitor legal homologado |
| 7 — Solar | **Engine v20 ampliado / dados externos e validação pendentes** | snapshots, DSM/surface/obstacles foundations, posição solar, POA explícito, shadows, energy, battery, tariff, grid precheck, ground-mount, safety, calibration, module packing, string/MPPT e financial projection | imagery/DSM/DEM reais, irradiância/tarifas/equipamentos versionados reais, OCR de conta em produção, BDGD/grid/provider, calibração nacional e revisão profissional |
| 8 — A.I TEC | **Engine avançado + fila/job/UI v20** | Site Solver, terrain/TIN, roads, parking/subsolo, Building/Unit/Room, environment, finance, Pareto, analyses/exports, job persistido com retry/backoff/metrics e UI job→worker→resultado | datasets reais, qualidade geométrica profissional, Design DNA final, IFC/DWG/BIM/licenças reais, canvas 2D/3D final e golden sites profissionais |
| 9 — Prefeitura | **Código operacional v20 / homologação institucional pendente** | onboarding, RBAC, datasets, CTM/CIB-SINTER/PGV/IPTU/ITBI/licenciamento, publication/rollback, open-data guard, recálculo, export/offboarding e AI institutional ACL | conexões/homologação reais com municípios/Receita/SINTER/CIB/fiscal/licenciamento e operação institucional acompanhada |
| 10 — Admin SaaS | **Código operacional avançado + billing UI v20 / providers pendentes** | tenant lifecycle, subscriptions/invoices/ledger/dunning/refund/chargeback, contracts/add-ons/coupons, fiscal orchestration, support sessions, CMS, analytics, AI Ops, rollout/release/rollback, RLS e UI billing→entitlement | Mercado Pago/NFS-e reais, UI profissional completa para suporte/CS/fiscal, métricas produtivas e approval/release executado em staging/prod |
| 11 — Escala nacional | **Municipality Factory implementada localmente** | connector contracts WFS/WMS/ArcGIS/CKAN/HTML/PDF/ZIP, discovery, snapshots/provenance, GIS/legal QA, candidate rules, golden lifecycle, publication preparation, change monitoring e coverage | packs/fontes oficiais por município, contratos/licenças, goldens profissionais, métricas nacionais alimentadas por produção e enterprise HA/DR |

## Lacunas transversais da Definition of Done — estado atual

1. **Browser/mobile/a11y:** implementado no PR #68, incluindo quatro jornadas críticas com controles visuais; ainda precisa execução integral verde e exploração manual final no Cortex.
2. **Segurança automatizável:** RLS, tenant leakage, authorization, AI red-team, security baseline, fault injection, supply-chain/SBOM e ZAP opcional existem; **pentest independente e fechamento dos achados continuam externos**.
3. **Carga/soak/capacidade:** perfis k6 multi-serviço existem e cobrem health, AI retrieval, Solar e A.I TEC; falta execução prolongada/medição no Cortex e staging real.
4. **Observabilidade:** RED HTTP, OTLP, Prometheus/Grafana/Loki/Tempo/Alertmanager, blackbox, fila A.I TEC, alerts/SLO/runbooks existem; falta exercício/medição operacional no ambiente alvo e owner/on-call final.
5. **Staging/release:** production parity, staging parity estrutural, promotion `image@sha256`, SBOM, canary contract e rollback drill existem; cloud/IaC/provider/IAM/secrets/DNS/TLS/registry reais continuam externos.
6. **Backup/DR:** DB + object storage são restaurados localmente com checksums e RPO/RTO sintéticos; PITR/failover/HA/DR de produção com RPO/RTO reais continuam externos.
7. **LGPD:** pedidos do titular, retenção, legal hold, append-only, export/erasure e guards estão implementados/testáveis; integrações externas/IdP exigem processo do sistema responsável e evidência real.
8. **Fontes/licenças/provenance:** contracts e guards existem; datasets só podem ser promovidos com evidência real. Ausência permanece `NOT_AVAILABLE`.
9. **Revisão profissional:** jurídica/engenharia/arquitetura/fiscal/institucional continua externa onde aplicável.
10. **Branch protection:** `main` continua dependente de configuração administrativa do GitHub (#21).

## Evidência runtime já consolidada

O runtime-e2e #60 fechou a race histórica entre `PUT` no OpenSearch e refresh do índice usando `refresh=wait_for` antes de `indexed_at`.

O artefato #60 comprovou documento privado A recuperável, ausência de vazamento do documento privado B para A, documento público somente com escopo explícito, corte temporal de documento futuro, OpenSearch single-node `yellow` com primárias ativas, Municipality Factory guards/RLS, A.I TEC runtime e backup/restore.

O PR #68 amplia essa base, mas **não será tratado como evidência verde até GitHub Actions/Cortex executarem os steps reais**.

## Caminho crítico final

1. Executar CI/runtime do head do PR #68 com runner real; corrigir qualquer falha até verde.
2. Executar `bash ops/cortex/qualify-local.sh ci`, depois `soak` e `capacity`; corrigir todos os bugs encontrados e repetir.
3. Fazer exploração visual/manual dos workspaces e ZAP/vulnerability tooling autorizado quando disponível.
4. Mergear #68 em `develop` somente após os gates locais verdes e evidências preservadas.
5. Executar fontes/providers oficiais, golden lots e revisões profissionais.
6. Selecionar/provisionar cloud/IaC, staging equivalente, secrets/IAM/DNS/TLS/registry e artefatos assinados.
7. Executar pentest, canary/rollback, PITR/HA/DR e RPO/RTO reais.
8. Proteger `main`, fechar riscos bloqueadores e só então alterar `productionHomologated`.

## Regra de aceite

O Blueprint considera concluído apenas o que possui os gates aplicáveis de implementação, teste, integração, dados/provenance e operação/homologação. Fixture, contrato sintético, SBOM ou status manual não substituem evidência real quando o requisito é externo/profissional.
