# LoteDiretor v20 — Runbooks operacionais

Estes runbooks são procedimentos reproduzíveis para ambiente local/staging e base para operação futura. Eles não substituem owner/on-call, pentest, DR ou homologação de produção.

## Service or database down

Alerta: `LoteDiretorServiceDown`.

1. Confirmar o target em Prometheus e identificar o `service` afetado.
2. Executar `docker compose ps -a` e capturar `docker compose logs --no-color --timestamps <service>`.
3. Verificar health do serviço e, para `platform-api`/`control-api`, conectividade e readiness do PostgreSQL correspondente.
4. Não contornar RLS usando role owner para restabelecer tráfego de aplicação.
5. Se a falha seguir mudança recente, iniciar o procedimento de rollback somente com digest imutável anterior e compatibilidade de migration comprovada.
6. Após recuperação, executar smoke, isolamento RLS e o gate específico do domínio afetado; registrar início, recuperação, causa e evidência.

## Prometheus target missing

Alerta: `LoteDiretorTargetMissing`.

1. Abrir `/api/v1/targets` no Prometheus e verificar `lastError`/`scrapeUrl`.
2. Confirmar que `/metrics` responde dentro da rede Compose e não exige autenticação de usuário.
3. Validar DNS/service name e profile `ops` do Compose.
4. Não desabilitar o alerta para “corrigir” o incidente. Se o serviço deliberadamente deixar de existir, alterar simultaneamente scrape config, SLO e documentação.

## High HTTP 5xx rate

Alertas: `LoteDiretorHigh5xxRate` e `LoteDiretorCritical5xxRate`.

1. Identificar serviço e janela no recording rule `lotediretor:http_5xx:ratio5m`.
2. Correlacionar `x-trace-id`/`traceparent` com Tempo e logs Loki/Compose.
3. Separar erro de aplicação, dependency timeout, DB/OpenSearch e provider externo.
4. Verificar saturação e rodar o profile k6 `ci` somente se isso não agravar um incidente real.
5. Para AI, preservar fail-closed/abstenção; nunca relaxar ACL, filtro temporal ou high-risk gate para reduzir 5xx.
6. Se rollback for necessário, seguir `ops/release/rollback-drill.sh` e registrar evidência.

## High p95 latency

Alerta: `LoteDiretorHighP95Latency`.

1. Confirmar `lotediretor:http_latency:p95_5m` e volume de requests para evitar interpretação de amostra insuficiente.
2. Correlacionar traces lentos com logs e dependências.
3. Verificar PostgreSQL, OpenSearch, CPU/memória e latência de providers externos antes de aumentar timeouts.
4. Executar `LOAD_PROFILE=capacity bash ops/load/run.sh` somente em ambiente isolado/Cortex/staging.
5. Não mover processamento pesado para request síncrona apenas para simplificar teste; usar jobs quando o Blueprint exigir processamento assíncrono.

## A.I TEC job queue or worker failure

Alertas: `LoteDiretorAitecWorkerDown`, `LoteDiretorAitecWorkerDbStale`, `LoteDiretorAitecQueueBacklog`, `LoteDiretorAitecQueueStalled`, `LoteDiretorAitecQueueCriticallyStalled`, `LoteDiretorAitecJobFailures` e `LoteDiretorAitecRetryStorm`.

1. Confirmar o target `aitec-worker` e as séries `lotediretor_aitec_jobs`, `lotediretor_aitec_oldest_job_age_seconds`, `lotediretor_aitec_job_executions_total`, `lotediretor_aitec_job_stale_reclaims_total` e `lotediretor_aitec_worker_last_db_success_unixtime`.
2. Executar `docker compose ps aitec-worker aitec-engine platform-db` e preservar logs dos três componentes antes de reiniciar qualquer processo.
3. Se o worker estiver vivo mas `last_db_success` estiver stale, validar DNS, credenciais da role `lotediretor_worker`, PostgreSQL e migrations `213_v20_aitec_jobs.sql`/`214_v20_aitec_job_retry_schedule.sql`; não substituir a role por owner/migration user.
4. Para backlog, comparar profundidade e idade da fila. Aumentar concorrência/capacidade só após confirmar que o engine e o banco suportam o novo limite; não apagar jobs para reduzir a métrica.
5. Para retries, diferenciar `429/5xx/unreachable` de falha não-retryable de contrato/contexto. Mismatch de tenant, projeto ou constraint é fail-closed e nunca deve ser convertido em retry permissivo.
6. Jobs retryable usam `next_attempt_at` e backoff persistente. Jobs `RUNNING` stale são reencaminhados apenas até `AITEC_JOB_MAX_ATTEMPTS`; após o limite devem terminar `FAILED`, com evento `aitec.job.failed` e evidência preservada.
7. Após recuperação, executar o E2E `A.I TEC job`, o teste de trust boundary do worker, RLS runtime e o profile k6 `ci`. Confirmar que nenhum job cross-tenant se tornou visível e que `professional_review_required=true` continua preservado.
8. Em produção, registrar quantidade afetada, duração do backlog, causa, retries, eventual rollback e owner da correção. Não classificar o incidente como encerrado apenas porque a fila voltou a zero.

## OIDC/login failure

1. Confirmar `/login`, `/api/v1/auth/start`, issuer público/interno e callback configurado.
2. Em ambiente local, o segredo do client importado deve coincidir com `infra/keycloak/realm-lotediretor.json`; nunca reutilizar esse fixture em produção.
3. Executar `bash ops/browser/run-e2e.sh` e preservar trace/video/screenshot.
4. Verificar atributos `HttpOnly`, `Secure` conforme ambiente e redirects permitidos.
5. Não criar bypass permanente de autenticação para fazer o E2E passar.

## OpenSearch retrieval empty or leaking

1. Executar `bash ops/ai/runtime-integration.sh`.
2. Confirmar saúde do cluster, index correto, contagem de documentos e logs `ai-ingest`/`ai-gateway`.
3. `ingest.document_text.indexed_at` significa search-ready; o worker usa refresh de escrita antes de marcar readiness.
4. Validar separadamente tenant privado, evidência pública opt-in e corte temporal.
5. Nunca remover filtros tenant/public/temporal como mitigação.

## Backup or restore drill failure

1. Preservar o diretório original do backup e `runtime-artifacts/dr`; não editar `METADATA.txt`, dumps ou o manifesto para fazer o drill passar.
2. Rodar `(cd <backup> && sha256sum -c SHA256SUMS.txt)` antes de qualquer restore. `METADATA.txt` deve fazer parte do próprio manifesto.
3. Verificar `backup_started_epoch`/`backup_completed_epoch`; timestamp ausente ou inconsistente invalida a medição do restore point.
4. Rodar `ops/backup/restore-drill.sh <backup>` somente em alvo isolado. O script deve usar databases e bucket temporários; nunca apontar o drill local para bancos/bucket de produção.
5. Exigir restore dos dois bancos, migrations não vazias, contratos críticos (`iam.organization`, `aitec.job`, `report.report_run`, `billing.invoice`, `ops.dr_drill`) e comparação SHA-256 do object storage restaurado.
6. Preservar o JSON `runtime-artifacts/dr/dr-*.json`. Em Cortex/local ele deve estar classificado `LOCAL_SYNTHETIC_DR_EVIDENCE_NOT_PRODUCTION_HOMOLOGATION` e conter RPO/RTO sintéticos.
7. RPO/RTO de produção exigem falha real/controlada em staging production-like ou produção autorizada, último ponto durável/PITR, timestamps reais, validação pós-restore e dependências externas. Nunca promover o valor local para SLO produtivo.

## Observability pipeline failure

1. Rodar `bash ops/observability/runtime-gate.sh` com profiles `full,ops` e override `docker-compose.ops.yml`.
2. Confirmar OTel Collector `:13133`, Tempo `:3200/ready`, Loki `:3100/ready`, Promtail `:9080/ready`, Alertmanager e Prometheus.
3. Verificar que platform/control/AI Gateway/Solar/A.I TEC engine e `aitec-worker` aparecem UP nos targets.
4. Para o worker, validar que `/metrics` contém profundidade/idade da fila e timestamp recente do último ciclo DB; target UP sozinho não prova processamento saudável.
5. Para o AI Gateway, exigir métricas RED nativas além do blackbox probe; probe verde sozinho não mede erro/latência internos.
6. Falha de telemetria não deve interromper uma request de negócio, mas deve impedir homologação operacional enquanto invisibilidade persistir.

## Canary and rollback

1. Canary deve apontar para URL explicitamente fornecida e executar smoke + AI eval + gate curto de carga.
2. Não promover quando taxa de erro/latência exceder thresholds, AI eval falhar ou houver alerta crítico.
3. Rollback exige digest imutável anterior, plano de migration compatível, integridade do backup e registro auditável.
4. Um script/checklist presente no repositório é apenas capacidade operacional; “rollback comprovado” exige execução real no ambiente candidato.

## Encerramento de incidente

Só encerrar após causa/mitigação registradas, checks reproduzíveis verdes e artefatos preservados. Falhas de fonte oficial, licença, provider ou revisão profissional permanecem classificadas como gate externo e não devem ser mascaradas por fixture local.
