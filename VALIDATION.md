# Validation — v20 development

Data da consolidação: 2026-08-25.

Esta evidência usa estados independentes para **implementação**, **validação estática/CI**, **validação runtime** e **homologação externa/profissional**. Código existente, fixture sintética ou um runtime local verde não substituem fonte oficial, credencial externa, revisão profissional ou gate de produção. `productionHomologated = false`.

## CI e regressão

A superfície histórica `validate-v19-rc3.sh` continua obrigatória durante o desenvolvimento v20. GitHub Actions executa `npm ci` com lockfile versionado, regressões RC3, validators v20, typecheck, builds e validação dos modelos Compose.

O Core Territorial/Legal possui corpus golden v20 sintético e versionado que executa o comportamento real do engine para `PERMITTED`, `PROHIBITED`, `UNKNOWN`, conflitos, vigência temporal, recuo dependente de altura, CEPAC, TDC e bloqueio de regra `CANDIDATE`. Isso prova regressão determinística, não legislação municipal.

## Runtime local/reproduzível — PASS

O PR #34 foi mergeado em `develop` no commit `71287ffde8590c89fcfb570c040a7f215892ac69` após `ci` run `32839748000` PASS e `runtime-e2e` run `32839747999` PASS.

O gate executou, em runner GitHub limpo:

- build reproduzível das imagens de aplicação;
- `docker compose` full-stack e health dos serviços;
- migrations PostgreSQL/PostGIS;
- smoke de gateway e serviços roteados;
- isolamento RLS cross-tenant com role de aplicação não-owner;
- OpenSearch real e bootstrap do índice de evidências;
- ai-ingest real e retrieval pelo caminho OpenSearch → AI Gateway → Caddy com assertions de tenant/public/municipality/temporal isolation;
- backup + restore drill;
- diagnóstico e cleanup do stack.

## AI lifecycle/evals — PASS na base atual

O PR #43 foi mergeado em `develop` no commit `8802b27878d0a745dcc9290a4de2ae564265964b` após `ci` run `32840808815` PASS e `runtime-e2e` run `32840808863` PASS.

A entrega inclui schema de índice `evidence-v20.1`, fingerprint estável do espaço vetorial por modelo/revisão/dimensão, recusa de reutilização de índice incompatível, rebuild/requeue explícito com confirmação destrutiva e golden evaluation do reranker determinístico com Recall@K, MRR e NDCG. Os contratos RC3 de ACL, temporalidade e mapping permanecem guards executáveis.

A ausência de provider externo não é mascarada: o runtime local real funciona lexicalmente e os providers de embeddings/chat continuam opcionais e explicitamente não homologados sem credenciais/evidência de qualidade.

## São Paulo ao vivo

Existem tooling de inspeção, streaming sync, preflight, publicação/promoção e candidatos/gates de golden lots. Isso ainda não constitui ingestão municipal homologada. Permanecem necessários acesso live, CRS/provenance/licença, QA, promoção canônica e 10–20 golden lots revisados por profissional.

## Gates ainda não homologados

Continuam pendentes providers externos de IA e sua qualidade/custo/fallback; fontes oficiais/licenciadas live; browser/mobile/a11y; observabilidade/SLO/alertas/runbooks; staging production-like; DNS/TLS/secrets/cloud IAM; pentest e red-team operacional; load/soak/capacity; canary/rollback; produção backup/restore e HA/DR com RPO/RTO; LGPD; revisão profissional aplicável; e branch protection de `main` (#21), observada como `protected=false` em 2026-08-25.

A matriz detalhada está em `docs/V20_ACCEPTANCE_MATRIX.md`.
