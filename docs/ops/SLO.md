# LoteDiretor v20 — SLO/SLI de pré-produção

Status: **candidatos operacionais para validação no Cortex/staging**. Estes valores não constituem SLO de produção homologado até que sejam medidos em ambiente equivalente à produção e formalmente aprovados. `productionHomologated=false` permanece obrigatório.

## Escopo

Os SLIs HTTP abaixo cobrem `platform-api`, `control-api`, `ai-gateway`, `solar-engine` e `aitec-engine` por métricas RED de baixa cardinalidade. A fila assíncrona A.I TEC possui SLIs próprios de profundidade, idade, retry e falha terminal. Fontes externas, providers de IA, revisões profissionais e qualidade/grounding possuem gates independentes e não podem ser reduzidos a disponibilidade HTTP.

## Disponibilidade HTTP

**SLI:** proporção de requisições concluídas que não retornam HTTP 5xx.

```promql
1 - (
  sum(rate(lotediretor_http_requests_total{status_class="5xx"}[30d]))
  /
  clamp_min(sum(rate(lotediretor_http_requests_total[30d])), 0.001)
)
```

**SLO candidato:** 99,9% mensal para APIs interativas homologadas. Em uma janela de 30 dias, isso corresponde a aproximadamente 43m49s de orçamento de indisponibilidade equivalente. O valor é um objetivo de engenharia, não uma medição atual.

O gate local/CI é mais curto e usa taxa de falha k6 inferior a 1%; ele detecta regressões, mas não substitui a medição mensal.

## Latência HTTP

**SLI:** histograma `lotediretor_http_request_duration_seconds` por serviço. A cardinalidade é limitada a `service`, `method` e `status_class`; paths, tenant IDs e IDs de recurso não são labels.

**Objetivo candidato para tráfego interativo:** p95 <= 1,5 s em janela de 5 minutos. O alerta `LoteDiretorHighP95Latency` dispara após 10 minutos acima desse limiar. Operações assíncronas de geração, exportação, visão, ingestão ou IA não devem ser transformadas artificialmente em endpoints síncronos para satisfazer esse alvo.

O AI Gateway participa do mesmo RED HTTP, mas sua aceitação funcional continua exigindo separadamente retrieval tenant/public/temporal, grounding, abstenção e high-risk fail-closed. Uma resposta rápida incorreta não satisfaz o produto.

## A.I TEC — fila assíncrona

A execução A.I TEC persistida é medida separadamente do request HTTP que apenas enfileira o trabalho.

**SLIs disponíveis:**

- profundidade por estado: `lotediretor_aitec_jobs{status}`;
- idade do job mais antigo por estado: `lotediretor_aitec_oldest_job_age_seconds{status}`;
- outcomes do worker: `lotediretor_aitec_job_executions_total{result}` com `completed`, `retry` e `failed`;
- stale reclaim: `lotediretor_aitec_job_stale_reclaims_total{result}`;
- duração da chamada ao solver: `lotediretor_aitec_engine_duration_seconds`;
- último ciclo DB bem-sucedido: `lotediretor_aitec_worker_last_db_success_unixtime`.

**Objetivos candidatos de pré-produção:**

- nenhum job `QUEUED` deve permanecer com idade > 120 s por mais de 5 minutos em carga nominal;
- idade > 600 s é condição crítica de fila travada;
- `aitec-worker` e seu ciclo DB não podem ficar invisíveis/stale por mais de 2 minutos;
- falha terminal deve permanecer excepcional e sempre gerar `aitec.job.failed`; retry não é contabilizado como sucesso nem usado para esconder indisponibilidade;
- retries transitórios usam backoff persistente, não hot-loop, e a recuperação deve concluir o mesmo `job_id` sem evento de conclusão duplicado.

Esses limiares são candidatos de engenharia. O profile `capacity`/soak em staging production-like deve medir vazão e tempo de fila antes de qualquer SLO final de jobs ser aprovado.

## Taxa de erro e alertas

Os recording rules HTTP são:

- `lotediretor:http_requests:rate5m`;
- `lotediretor:http_5xx:ratio5m`;
- `lotediretor:http_latency:p95_5m`.

Alertas candidatos HTTP:

- warning quando 5xx > 1% por 5 minutos;
- critical quando 5xx > 5% por 2 minutos;
- warning quando p95 > 1,5 s por 10 minutos;
- critical quando um serviço/DB ou target Prometheus fica indisponível por 2 minutos.

Alertas candidatos A.I TEC incluem worker/DB stale, backlog, fila stalled/crítica, falha terminal e retry storm. Os thresholds operacionais estão versionados em `infra/prometheus/rules/lotediretor.yml` e o procedimento em `docs/ops/RUNBOOKS.md`.

## Segurança e IA

Disponibilidade não pode sobrepor segurança. Respostas 401/403 legítimas não são erro de disponibilidade. Um AI Gateway que se abstém por falta de evidência/provider é preferível a uma resposta inventada; qualidade, grounding, ACL/tenant, bitemporalidade e high-risk gates permanecem critérios separados de SLO HTTP.

Métricas HTTP não carregam tenant, project, job, document ou resource IDs como labels. Identificadores necessários para investigação permanecem em traces/logs/evidência persistida, evitando cardinalidade explosiva e exposição acidental no plano de métricas.

## Dados e recuperação

Backup/restore local é um gate reproduzível. RPO/RTO de produção só pode ser definido como cumprido após um DR drill em infraestrutura equivalente à produção com timestamps de falha, último ponto recuperável, início/fim de restore e validação pós-restore. O harness pré-Cortex não converte um restore local em evidência de HA/DR de produção.

## Owners

Ownership de código está declarado em `.github/CODEOWNERS`. O owner operacional final/on-call deve ser definido no ambiente de produção antes do go-live. Não existe aprovação implícita pelo simples fato de o código ter um CODEOWNER.

## Critério para promover estes candidatos a SLO de produção

Exigir conjuntamente: Cortex local verde, staging production-like medido, capacidade/soak executados, alertas validados, runbooks exercitados, canary/rollback real, backup/DR real e ausência de risco crítico/alto aberto. Os resultados devem ser anexados ao relatório final do issue #13.
