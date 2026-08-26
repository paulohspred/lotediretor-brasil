# Status — v20 development

## Estado atual

O `develop` está em desenvolvimento v20 sobre o runtime versionado `19.0.0-rc.3`, preservando a superfície de regressão RC3. O baseline runtime consolidado desta evidência é `42ac9a13ccb726f68e48a62be75e7d5bec1ffaa7`, merge do PR #66.

**Implementação, CI, runtime, dados reais e homologação profissional/produção são gates independentes.** `productionHomologated = false`.

## Implementado e comprovado

- `package-lock.json`, `npm ci`, validators RC3/v20, typecheck, builds e validação Compose executam no GitHub Actions;
- o runtime Docker full-stack sobe em runner limpo e prova health, migrations PostgreSQL/PostGIS, smoke, RLS cross-tenant com role não-owner, OpenSearch/ai-ingest/retrieval isolation, A.I TEC v20, Municipality Factory e backup/restore;
- Core Territorial/Legal possui corpus golden v20 sintético e versionado para `PERMITTED`, `PROHIBITED`, `UNKNOWN`, conflito, vigência temporal, recuo dependente de altura, CEPAC, TDC e bloqueio de regra `CANDIDATE`;
- AI Core preserva ACL/tenant, bitemporalidade, lexical/hybrid retrieval com RRF, reranker legal, Prompt/Tool Registry, Model Router/fallback/circuit breaker, cache pinado, evidence/high-risk gates e red-team sintético;
- o índice de evidências possui schema `evidence-v20.1`, fingerprint por modelo/revisão/dimensão, recusa de mistura vetorial incompatível e rebuild/requeue explícito;
- o ai-ingest marca `indexed_at` somente após `refresh=wait_for`, de modo que o estado no PostgreSQL representa evidência já pesquisável no OpenSearch; a correção fechou a race observada no runtime #58;
- PR #66 foi mergeado em `develop` (`42ac9a13ccb726f68e48a62be75e7d5bec1ffaa7`) após `ci` #456 PASS e `runtime-e2e` #60 PASS; o artefato comprova retrieval privado do tenant A, ausência de vazamento do tenant B, inclusão pública municipal somente quando solicitada e exclusão temporal de regra futura;
- São Paulo possui contratos lote/zona, publicação por dataset, promoção canônica, ferramentas de inspeção/sync/preflight e candidatos/gates para golden lots, sem afirmar homologação live;
- A.I TEC v20 possui ingestão, terreno/TIN, viário, estacionamento/subsolo, Building Solver, Unit/Room Solver, ambiente, finanças, otimização/Pareto e exports, com runtime API provado; profundidade profissional/CAD-BIM real permanece gate separado;
- Solar v20 possui motor determinístico de cenários e design elétrico string/MPPT com inputs explícitos; dados externos, calibração e validação profissional permanecem separados;
- Imóvel 360/RE Rural receberam camada operacional v20 de mercado/readiness e dados tenant-scoped, sem converter ausência de fonte oficial em resposta positiva;
- Condomínio v20 possui governança operacional, lifecycle documental e guards tenant-scoped;
- Prefeitura v20 possui onboarding, datasets CTM/CIB-SINTER/PGV/IPTU/ITBI/licenciamento, publicação/rollback, open data guard, recálculo afetado, export materializado e offboarding auditado;
- Admin SaaS v20 possui lifecycle de billing/ledger/dunning/refund/chargeback, fiscal orchestration, support sessions, CMS, analytics/cohorts, AI Ops, rollout/release/rollback e FORCE RLS nas entidades tenant-owned;
- Municipality Factory v20 possui contratos de conectores, discovery seguro, snapshots/provenance, QA, rule candidates sem auto-homologação, golden cases, publication workflow, change monitoring e métricas nacionais de cobertura.

## Pendências que impedem 100% do Blueprint/homologação

O maior volume restante deixou de ser criação de motores-base e passou a ser **dados reais, UX/E2E e operação de produção**. São Paulo ainda exige fonte live, sync com CRS/provenance/licença, QA/promoção e 10–20 golden lots revisados por profissional. RE Rural/Imóvel 360, Prefeitura, Solar e demais domínios ainda dependem de fontes oficiais/licenciadas e/ou providers reais. Providers externos de IA exigem credenciais e avaliação real de qualidade/custo/fallback. A.I TEC/Solar exigem validação profissional e datasets/equipamentos reais onde aplicável.

## Gates de produção ainda separados

Continuam pendentes browser E2E/mobile/a11y; pentest e red-team operacional; load/soak/capacity por serviço; observabilidade/SLO/alertas/runbooks comprovados; staging production-like e IaC; DNS/TLS/secrets/cloud IAM; canary/rollback em ambiente alvo; HA/DR com RPO/RTO medidos; LGPD operacional; e revisão profissional aplicável. A branch `main` continua sem branch protection (`protected=false`) e o gate administrativo #21 permanece separado do código.

## Próxima ordem de fechamento

1. manter o runtime #60 como baseline verde e corrigir regressões sem relaxar isolamento/temporalidade;
2. fechar os gates de código do issue #13: browser/mobile/a11y, segurança automatizada, carga/capacidade, observabilidade/SLO/runbooks, staging/IaC, canary/rollback e LGPD operacionalizável;
3. executar São Paulo live + golden lots e demais fontes oficiais/licenciadas sem transformar fixture em verdade operacional;
4. executar avaliações profissionais/externas de IA, jurídico, engenharia, arquitetura, fiscal e dados quando aplicáveis;
5. proteger `main`, promover release candidate e somente então considerar `productionHomologated = true`.
