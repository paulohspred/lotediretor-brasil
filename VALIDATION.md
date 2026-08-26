# Validation — v20 development

Data da consolidação: 2026-08-26.

Esta evidência usa estados independentes para **implementação**, **validação estática/CI**, **validação runtime** e **homologação externa/profissional**. Código existente, fixture sintética ou um runtime local verde não substituem fonte oficial, credencial externa, revisão profissional ou gate de produção. `productionHomologated = false`.

## Baseline consolidado

O baseline runtime consolidado é `42ac9a13ccb726f68e48a62be75e7d5bec1ffaa7`, merge do PR #66 em `develop`.

O PR #66 fechou o incremento de Municipality Factory e a race de search-readiness do AI ingest. O worker agora usa OpenSearch `refresh=wait_for` antes de marcar `ingest.document_text.indexed_at`; portanto o estado do PostgreSQL não pode declarar um chunk indexado enquanto ele ainda estiver invisível para `_search`.

Validação do head do PR #66:

- `ci` run #456 → **PASS**;
- `runtime-e2e` run #60 → **PASS**;
- artefato runtime `9602867789` gerado e preservado pelo workflow.

## CI e regressão

A superfície histórica `validate-v19-rc3.sh` continua obrigatória durante o desenvolvimento v20. GitHub Actions executa `npm ci` com lockfile versionado, regressões RC3, validators v20, typecheck, builds e validação dos modelos Compose.

O Core Territorial/Legal possui corpus golden v20 sintético e versionado que executa o comportamento real do engine para `PERMITTED`, `PROHIBITED`, `UNKNOWN`, conflitos, vigência temporal, recuo dependente de altura, CEPAC, TDC e bloqueio de regra `CANDIDATE`. Isso prova regressão determinística, não legislação municipal.

## Runtime local/reproduzível — PASS

O runtime #60 executou em runner GitHub limpo:

- reclaim e verificação de disco do runner;
- build reproduzível das imagens de aplicação;
- `docker compose` full-stack e health dos serviços;
- migrations PostgreSQL/PostGIS;
- smoke de gateway e serviços roteados;
- A.I TEC v20 advanced runtime API;
- isolamento RLS cross-tenant com role de aplicação não-owner;
- Municipality Factory DB guards e tenant isolation;
- OpenSearch real e bootstrap do índice de evidências;
- ai-ingest real e retrieval pelo caminho OpenSearch → AI Gateway → Caddy;
- backup + restore drill;
- captura de diagnóstico e cleanup do stack.

O artefato do run #60 mostra o cluster OpenSearch `yellow`, esperado no CI single-node com réplica não alocada, mas com primárias ativas e runtime aprovado. A busca privada do tenant A retorna o chunk `0198f020-1000-7000-8000-000000000001`; a consulta pelo segredo do tenant B não retorna o documento B; o documento público municipal é recuperado somente quando `includePublic=true`; e a regra com vigência a partir de 2099 não é retornada para `baseDate=2026-08-23`.

## AI lifecycle/evals

O índice usa schema `evidence-v20.1`, fingerprint estável do espaço vetorial por modelo/revisão/dimensão, recusa de reutilização de índice incompatível, rebuild/requeue explícito com confirmação destrutiva e golden evaluation do reranker determinístico com Recall@K, MRR e NDCG. Os contratos de ACL, temporalidade e mapping permanecem guards executáveis.

A ausência de provider externo não é mascarada: o runtime real funciona lexicalmente quando embeddings não estão configurados. Providers de embeddings/chat continuam opcionais e explicitamente não homologados sem credenciais, custo e evidência de qualidade/fallback.

## Módulos v20 implementados depois da matriz antiga

A.I TEC já possui terrain/TIN, road engineering, basement parking, Building/Unit/Room Solver, environment, finance, optimization/Pareto e export stack. Prefeitura/B2G possui onboarding, dataset publication/rollback, CTM/CIB-SINTER/PGV/IPTU/ITBI/licenciamento, open-data guard, affected recalculation, materialized export e offboarding. Admin SaaS possui billing/ledger/dunning/refund/chargeback, fiscal orchestration, support sessions, CMS, analytics/cohorts, AI Ops e release/rollback. Condomínio, Imóvel 360/RE Rural e Solar também receberam incrementos operacionais v20. Municipality Factory foi mergeada pelo PR #66.

Essas implementações não eliminam os gates de dados reais, UX/browser, produção e revisão profissional.

## São Paulo ao vivo

Existem tooling de inspeção, streaming sync, preflight, publicação/promoção e candidatos/gates de golden lots. Isso ainda não constitui ingestão municipal homologada. Permanecem necessários acesso live, CRS/provenance/licença, QA, promoção canônica e 10–20 golden lots revisados por profissional.

## Gates ainda não homologados

Continuam pendentes providers externos de IA e sua qualidade/custo/fallback; fontes oficiais/licenciadas live; browser/mobile/a11y; observabilidade/SLO/alertas/runbooks; staging production-like e IaC; DNS/TLS/secrets/cloud IAM; pentest e red-team operacional; load/soak/capacity; canary/rollback em ambiente alvo; produção backup/restore e HA/DR com RPO/RTO medidos; LGPD operacional; revisão profissional aplicável; e branch protection de `main` (#21), observada como `protected=false` em 2026-08-26.

A matriz detalhada está em `docs/V20_ACCEPTANCE_MATRIX.md`.
