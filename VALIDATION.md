# Validation — v20 development

Data da consolidação: 2026-08-26.

Esta evidência mantém estados independentes para **implementação**, **validação executada**, **runtime** e **homologação externa/profissional**. Código existente, fixture sintética, SBOM, scan automatizado ou runtime local verde não substituem fonte oficial, credencial externa, revisão profissional ou gate de produção. `productionHomologated = false`.

## Baseline consolidado e realmente verde

O baseline validado em `develop` é `52ed13cc37109c02016b513113b13ab951c3bc9a`, merge do PR #67.

Validação desse baseline:

- `ci` run #469 → **PASS**;
- `runtime-e2e` run #62 → **PASS**.

O PR #67 sucede o PR #66 e mantém a correção da race de search-readiness do AI ingest: OpenSearch usa `refresh=wait_for` antes de `ingest.document_text.indexed_at`, impedindo PostgreSQL de declarar search-ready um chunk ainda invisível a `_search`.

## Candidato pré-Cortex — PR #68

O PR #68 concentra os gates implementáveis de go-live. O código está em estado **pre-Cortex code-complete**, porém o candidato **não está validado** enquanto os GitHub-hosted jobs terminarem antes de executar steps (`steps=[]`, sem logs de job).

Implementado no candidato:

- Playwright real com Keycloak/OIDC, desktop/mobile e axe WCAG A/AA;
- quatro jornadas críticas exigidas pelo Blueprint: `resolver → análise → relatório`, `billing → entitlement`, `condo upload → chat` e `A.I TEC job`;
- A.I TEC job persistido assíncrono, worker, RLS, idempotência, allowlist, retry/backoff, stale reclaim, métricas, alertas e fault recovery;
- AI retrieval tenant/public/temporal, provenance, RED/OTLP e red-team determinístico contra prompt injection, tenant leakage, high-risk e tool/action boundaries;
- privacy/LGPD com retenção, legal hold, requests do titular, erasure/export, session revocation e append-only evidence;
- k6 `ci/soak/capacity` multi-serviço;
- RED/OTLP dos cinco serviços HTTP, Prometheus/Grafana/Loki/Tempo/Promtail/Alertmanager/blackbox e SLIs da fila A.I TEC;
- fault injection controlado;
- production parity, structural staging parity, promoção `image@sha256`, rollback self-test e canary com AI eval;
- supply-chain inventory + CycloneDX 1.5 SBOM e guard de imagens flutuantes;
- Trivy 0.73.0 para filesystem/dependências/misconfiguration/secrets e scan de imagens locais no Cortex, bloqueando HIGH/CRITICAL corrigíveis;
- backup/restore de PostgreSQL e object storage com checksums, assertions de schema e RPO/RTO sintéticos locais;
- `ops/cortex/qualify-local.sh` com ledger de gates, `qualification-report.json/.md` e `evidence-manifest.json`.

Esses itens estão **implementados, não homologados** até que o head correspondente execute e produza evidência verde.

## CI e regressão

A superfície histórica `validate-v19-rc3.sh` continua obrigatória durante v20. O CI do candidato também inclui validators v20, typecheck, builds, Compose local/full/produção, Prometheus rules, production parity, staging parity estrutural, immutable release/rollback e supply-chain contracts.

O Core Territorial/Legal mantém corpus golden v20 sintético e versionado para `PERMITTED`, `PROHIBITED`, `UNKNOWN`, conflitos, temporalidade, recuo dependente de altura, CEPAC, TDC e bloqueio de regra `CANDIDATE`. Isso é regressão determinística, não legislação municipal homologada.

## Runtime baseline comprovado

O runtime #62 é a evidência mergeada mais recente. Ele sucede o runtime #60 e mantém full-stack build/startup, migrations, service smoke, A.I TEC runtime, non-owner RLS, Municipality Factory guards e OpenSearch/AI isolation.

Em evidências CI single-node, OpenSearch `yellow` com primárias ativas é aceitável para o gate local e não é tratado como HA de produção. Tenant/private/public/temporal retrieval permanecem critérios separados de health do cluster.

## AI lifecycle/evals

O índice usa schema `evidence-v20.1`, fingerprint estável de espaço vetorial, recusa de índice incompatível, rebuild/requeue explícito e golden evals determinísticos. Providers externos não são inventados como homologados: sem provider, o runtime pode operar lexicalmente; provider/model/embedding configurado exige avaliação separada de qualidade, custo, fallback e red-team.

## Módulos v20

A.I TEC, Prefeitura/B2G, Admin SaaS, Condomínio, Imóvel 360/RE Rural, Solar e Municipality Factory possuem implementação operacional v20. O PR #68 adiciona ainda jornadas browser críticas e aprofundamentos de Solar/A.I TEC/quality gates. Isso não elimina a necessidade de dados reais, licenças, calibração e revisão profissional onde o Blueprint exige.

## São Paulo e fontes live

Existem tooling de inspeção, streaming sync, preflight, publicação/promoção e candidatos/gates de golden lots. Isso não constitui ingestão municipal homologada. Permanecem necessários acesso live, CRS/provenance/licença, QA, promoção canônica e 10–20 golden lots revisados profissionalmente.

## Gates externos ainda não homologados

Continuam pendentes:

- pentest independente e fechamento de achados Critical/High;
- provider/model/embeddings reais com avaliação de qualidade/custo/fallback/red-team específico;
- fontes oficiais/licenciadas live, contratos/licenças/provenance e dados/calibração reais;
- revisões jurídica, engenharia, arquitetura, fiscal e institucional aplicáveis;
- cloud/IaC escolhido, IAM/secrets/DNS/TLS/registry e staging production-like realmente implantado;
- assinatura de imagens e build/provenance attestations no registry final;
- canary/rollback real;
- produção PITR/failover/HA/DR com RPO/RTO reais;
- branch protection de `main` (#21), ainda observada como `protected=false` em 2026-08-26.

## Próximo critério de aceitação

O PR #68 só pode ser mergeado após execução real de CI/runtime/security e/ou Cortex no mesmo head, correção de toda falha encontrada e `localQualificationStatus=PASS`. Depois disso, os gates externos seguem como trilha separada até ser legítimo considerar `productionHomologated=true`.

A matriz detalhada está em `docs/V20_ACCEPTANCE_MATRIX.md`.
