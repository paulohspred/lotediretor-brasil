# Status — v20 development

## Estado atual

O `develop` está em desenvolvimento v20 sobre o runtime versionado `19.0.0-rc.3`, preservando a superfície de regressão RC3. O baseline consolidado desta evidência é `8802b27878d0a745dcc9290a4de2ae564265964b`.

**Implementação, CI, runtime, dados reais e homologação profissional/produção são gates independentes.** `productionHomologated = false`.

## Implementado e comprovado

- `package-lock.json`, `npm ci`, validators RC3/v20, typecheck, builds e validação Compose executam no GitHub Actions;
- o runtime Docker full-stack sobe em runner limpo e prova health, migrations PostgreSQL/PostGIS, smoke, RLS cross-tenant com role não-owner, OpenSearch/ai-ingest/retrieval isolation e backup/restore;
- PR #34 foi mergeado em `develop` (`71287ffde8590c89fcfb570c040a7f215892ac69`) após `ci` 32839748000 PASS e `runtime-e2e` 32839747999 PASS;
- Core Territorial/Legal possui corpus golden v20 sintético e versionado para `PERMITTED`, `PROHIBITED`, `UNKNOWN`, conflito, vigência temporal, recuo dependente de altura, CEPAC, TDC e bloqueio de regra `CANDIDATE`; PR #41 foi mergeado com CI verde;
- AI Core preserva ACL/tenant, bitemporalidade, lexical/hybrid retrieval com RRF, reranker legal, Prompt/Tool Registry, Model Router/fallback/circuit breaker, cache pinado, evidence/high-risk gates e red-team sintético;
- o índice de evidências possui schema `evidence-v20.1`, fingerprint por modelo/revisão/dimensão, recusa de mistura vetorial incompatível e rebuild/requeue explícito;
- o reranker determinístico possui golden eval sintético com Recall@K, MRR e NDCG; PR #43 foi mergeado em `develop` (`8802b27878d0a745dcc9290a4de2ae564265964b`) após `ci` 32840808815 PASS e `runtime-e2e` 32840808863 PASS;
- São Paulo possui contratos lote/zona, publicação por dataset, promoção canônica, ferramentas de inspeção/sync/preflight e candidatos/gates para golden lots, mas isso não equivale a homologação live;
- A.I TEC mantém Site Solver, parking geométrico, acesso explícito, locks/branch/regenerate, unit mix, cut/fill conceitual, Building Stack, análises e exports;
- Solar mantém o design elétrico preliminar string/MPPT somente com dados explícitos.

## Pendências que impedem 100% do Blueprint/homologação

São Paulo ainda exige fonte live, sync com CRS/provenance, QA/promoção e 10–20 golden lots revisados por profissional. Providers externos de IA ainda exigem avaliação real de qualidade/custo/fallback. A.I TEC avançado ainda requer terreno/parking/Building+Unit Solver/CAD-BIM em profundidade de engenharia. Solar ainda requer imagery/DSM/DEM, roof/obstacles/3D shadows, tarifas/OCR/grid/estrutura/calibração. Também permanecem Imóvel 360/RE Rural avançado, Condomínio 360, Prefeitura, Admin SaaS e Municipality Factory.

## Gates de produção ainda separados

Continuam pendentes browser/mobile/a11y, observabilidade/SLO/runbooks, staging production-like, DNS/TLS/secrets/cloud IAM, pentest, load/soak/capacity, canary/rollback, HA/DR com RPO/RTO, LGPD e revisão profissional aplicável. A branch `main` foi observada com `protected=false` em 2026-08-25 e o gate administrativo #21 permanece aberto.

## Próxima ordem de fechamento

1. sincronizar esta evidência v20 em `develop`;
2. fechar São Paulo live + golden lots sem converter fixtures em verdade municipal;
3. aprofundar Core/Legal onde faltarem instrumentos e golden cases reais;
4. completar A.I TEC e Solar avançados;
5. completar os módulos de produto restantes;
6. executar os gates externos/profissionais de produção e somente então considerar `productionHomologated = true`.
