# Status — v20 pre-Cortex

## Estado atual

O baseline **já validado e mergeado** em `develop` é `52ed13cc37109c02016b513113b13ab951c3bc9a` (PR #67), com CI #469 e runtime-e2e #62 PASS. O PR #68 concentra a qualificação v20 pré-Cortex e **não está validado/mergeado** enquanto os GitHub-hosted jobs continuarem terminando antes de executar steps (`steps=[]`/sem logs de job).

Implementação, validação estática, runtime, dados reais e homologação profissional/produção são gates independentes. `productionHomologated=false`.

## Implementado no PR #68 — ainda exige execução integral verde

- Docker Compose local padrão inclui `aitec-worker` via `docker-compose.override.yml`; CI/Cortex/produção usam overlays explícitos;
- Playwright real via Keycloak/OIDC, desktop/mobile, axe WCAG A/AA, traces/screenshots/video;
- quatro jornadas críticas com caminho visual real: Imóvel `resolver → análise → relatório`, Admin `subscription → invoice → payment → entitlement`, Condomínio `upload privado → indexação → A.I Condomínio`, A.I TEC `projeto → job persistido → worker → resultado`;
- A.I TEC possui fila `aitec.job`, idempotência, allowlist, RLS, worker cross-tenant least-privilege, retry/backoff `next_attempt_at`, stale reclaim, métricas, alertas e fault-recovery do mesmo `job_id`;
- AI Core possui retrieval tenant/public/temporal, provenance, RED/OTLP e red-team runtime local com evidência hostil recuperada, high-risk fail-closed, tenant leakage e write-tool explicit action;
- k6 `ci/soak/capacity` mede health, AI retrieval, Solar e A.I TEC;
- observabilidade cobre RED dos cinco serviços HTTP, OTel/Tempo, Prometheus/Grafana/Loki/Promtail/Alertmanager/blackbox e SLIs da fila A.I TEC;
- privacy/LGPD inclui requests do titular, retenção, legal hold, erasure/export, revogação de sessão, RLS e append-only;
- production parity, staging parity estrutural, promoção `image@sha256`, rollback self-test e canary com AI eval;
- supply-chain inventory + CycloneDX SBOM, imagens MinIO explicitamente versionadas e guard contra referências flutuantes;
- Trivy 0.73.0 automatiza filesystem/dependency/misconfiguration/secret scan e, no Cortex, scan das imagens locais; findings corrigíveis HIGH/CRITICAL bloqueiam o gate;
- backup/restore de PostgreSQL e object storage com checksums, assertions de schema e RPO/RTO sintéticos locais;
- harness `ops/cortex/qualify-local.sh` registra gates e produz `qualification-report` + `evidence-manifest`.

## Evidência já consolidada

O runtime-e2e #62 do PR #67 é a evidência verde mais recente do baseline mergeado em `develop`. Ele sucede a evidência #60 e mantém os contratos de runtime/AI já validados sem afirmar HA de produção. Em evidências single-node do OpenSearch, status `yellow` com primárias ativas é aceitável para o gate local e **não** equivale a HA de produção.

## Pendências implementáveis que agora são principalmente de execução/correção

1. executar o head do #68 em runner/Cortex com steps reais;
2. corrigir toda falha de typecheck/build/Compose/runtime/browser/a11y/security/Trivy/load/fault/observability/DR encontrada;
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
- política final de CVEs, assinatura de imagens e build/provenance attestations no registry final;
- proteção administrativa da `main` (#21), atualmente `protected=false`.

## Regra de fechamento

Fixture, contrato local, SBOM, scan automatizado, status manual ou job do GitHub sem steps não é homologação. O próximo marco técnico é **PR #68 + Cortex local integralmente verdes**; somente depois avançam os gates externos até ser legítimo considerar `productionHomologated=true`.
