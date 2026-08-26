# Status — v20 pre-Cortex

## Estado atual

O baseline **já validado e mergeado** permanece `42ac9a13ccb726f68e48a62be75e7d5bec1ffaa7` (`develop`, PR #66), com CI #456 e runtime-e2e #60 PASS. O PR #68 concentra a qualificação v20 pré-Cortex e **não está validado/mergeado** enquanto os GitHub-hosted jobs continuarem terminando com `runner_id=0` e `steps=[]`.

Implementação, validação estática, runtime, dados reais e homologação profissional/produção são gates independentes. `productionHomologated=false`.

## Implementado no PR #68 — ainda exige execução integral verde

- Docker Compose local padrão inclui `aitec-worker`; CI/Cortex/produção usam overlays explícitos;
- Playwright real via Keycloak/OIDC, desktop/mobile, axe WCAG A/AA, traces/screenshots/video;
- quatro jornadas críticas com caminho visual real: Imóvel `resolver → análise → relatório`, Admin `subscription → invoice → payment → entitlement`, Condomínio `upload privado → indexação → A.I Condomínio`, A.I TEC `projeto → job persistido → worker → resultado`;
- A.I TEC possui fila `aitec.job`, idempotência, allowlist, RLS, worker cross-tenant least-privilege, retry/backoff `next_attempt_at`, stale reclaim, métricas, alertas e fault-recovery do mesmo `job_id`;
- AI Core possui retrieval tenant/public/temporal, provenance, RED/OTLP e red-team runtime local com evidência hostil recuperada, high-risk fail-closed, tenant leakage e write-tool explicit action;
- k6 `ci/soak/capacity` mede health, AI retrieval, Solar e A.I TEC;
- observabilidade cobre RED dos cinco serviços HTTP, OTel/Tempo, Prometheus/Grafana/Loki/Promtail/Alertmanager/blackbox e SLIs da fila A.I TEC;
- privacy/LGPD inclui requests do titular, retenção, legal hold, erasure/export, revogação de sessão, RLS e append-only;
- production parity, staging parity estrutural, promoção `image@sha256`, rollback self-test e canary com AI eval;
- supply-chain inventory + CycloneDX SBOM, imagens MinIO explicitamente versionadas e guard contra referências flutuantes;
- backup/restore de PostgreSQL e object storage com checksums, assertions de schema e RPO/RTO sintéticos locais;
- harness `ops/cortex/qualify-local.sh` registra gates e produz `qualification-report` + `evidence-manifest`.

## Evidência já consolidada

O runtime #60 continua sendo a evidência verde mais recente: full stack, migrations, smoke, A.I TEC v20 API, non-owner RLS, Municipality Factory, OpenSearch/ai-ingest tenant/public/temporal isolation e backup/restore. O OpenSearch dessa evidência foi `yellow` single-node com primárias ativas; isso não é HA de produção.

## Pendências implementáveis que agora são principalmente de execução/correção

1. executar o head do #68 em runner/Cortex com steps reais;
2. corrigir toda falha de typecheck/build/Compose/runtime/browser/a11y/security/load/fault/observability/DR encontrada;
3. executar `ci`, depois `soak` e `capacity` no Cortex e repetir até `localQualificationStatus=PASS`;
4. fazer exploração visual/manual dos módulos e corrigir bugs/UX residual sem relaxar os gates;
5. mergear #68 em `develop` somente após evidência verde reproduzível.

## Gates externos que continuam impedindo 100% de homologação

- pentest independente e fechamento de todos os achados Critical/High;
- provider/model/embeddings reais e red-team específico do provider;
- São Paulo live e demais fontes oficiais/licenciadas, provenance/licença e golden lots revisados;
- comparáveis/AVM/dados rurais/solar/municipais reais e calibrações aplicáveis;
- revisão jurídica, arquitetura, engenharia, fiscal e institucional onde exigida;
- escolha/provisionamento do cloud/IaC, IAM/secrets/DNS/TLS/registry reais;
- staging production-like executado, canary/rollback real, PITR/failover/HA/DR com RPO/RTO reais;
- CVE policy, assinatura/attestation de imagens no registry final;
- proteção administrativa da `main` (#21).

## Regra de fechamento

Fixture, contrato local, SBOM, status manual ou job do GitHub sem steps não é homologação. O próximo marco técnico é **PR #68 + Cortex local integralmente verdes**; somente depois avançam os gates externos até ser legítimo considerar `productionHomologated=true`.
