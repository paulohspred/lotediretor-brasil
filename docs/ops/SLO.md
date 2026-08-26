# LoteDiretor v20 — SLO/SLI de pré-produção

Status: **candidatos operacionais para validação no Cortex/staging**. Estes valores não constituem SLO de produção homologado até que sejam medidos em ambiente equivalente à produção e formalmente aprovados. `productionHomologated=false` permanece obrigatório.

## Escopo

Os SLIs abaixo cobrem `platform-api`, `control-api`, `solar-engine` e `aitec-engine` por métricas RED de baixa cardinalidade. O AI Gateway possui gates próprios de evidência/abstenção e deve ser incluído no plano de métricas HTTP antes da homologação final. Fontes externas, providers de IA e revisões profissionais possuem gates independentes.

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

## Latência

**SLI:** histograma `lotediretor_http_request_duration_seconds` por serviço. A cardinalidade é limitada a `service`, `method` e `status_class`; paths, tenant IDs e IDs de recurso não são labels.

**Objetivo candidato para tráfego interativo:** p95 <= 1,5 s em janela de 5 minutos. O alerta `LoteDiretorHighP95Latency` dispara após 10 minutos acima desse limiar. Operações assíncronas de geração, exportação, visão, ingestão ou IA não devem ser transformadas artificialmente em endpoints síncronos para satisfazer esse alvo.

## Taxa de erro

Os recording rules são:

- `lotediretor:http_requests:rate5m`;
- `lotediretor:http_5xx:ratio5m`;
- `lotediretor:http_latency:p95_5m`.

Alertas candidatos:

- warning quando 5xx > 1% por 5 minutos;
- critical quando 5xx > 5% por 2 minutos;
- warning quando p95 > 1,5 s por 10 minutos;
- critical quando um serviço/DB ou target Prometheus fica indisponível por 2 minutos.

## Segurança e IA

Disponibilidade não pode sobrepor segurança. Respostas 401/403 legítimas não são erro de disponibilidade. Um AI Gateway que se abstém por falta de evidência/provider é preferível a uma resposta inventada; qualidade, grounding, ACL/tenant, bitemporalidade e high-risk gates permanecem critérios separados de SLO HTTP.

## Dados e recuperação

Backup/restore local é um gate reproduzível. RPO/RTO de produção só pode ser definido como cumprido após um DR drill em infraestrutura equivalente à produção com timestamps de falha, último ponto recuperável, início/fim de restore e validação pós-restore. O harness pré-Cortex não converte um restore local em evidência de HA/DR de produção.

## Owners

Ownership de código está declarado em `.github/CODEOWNERS`. O owner operacional final/on-call deve ser definido no ambiente de produção antes do go-live. Não existe aprovação implícita pelo simples fato de o código ter um CODEOWNER.

## Critério para promover estes candidatos a SLO de produção

Exigir conjuntamente: Cortex local verde, staging production-like medido, capacidade/soak executados, alertas validados, runbooks exercitados, canary/rollback real, backup/DR real e ausência de risco crítico/alto aberto. Os resultados devem ser anexados ao relatório final do issue #13.
