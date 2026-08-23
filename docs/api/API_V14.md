# API v14 — contratos transversais

## REST

Prefixo externo: `/api/v1`.

Documento OpenAPI baseline: `GET /api/v1/openapi.json`.

### Erro padrão

```json
{
  "code": "module_not_entitled",
  "message": "module_not_entitled",
  "fields": {},
  "trace_id": "...",
  "retryable": false
}
```

### Idempotência

Comandos marcados como idempotentes aceitam `Idempotency-Key`. A chave é persistida por `tenant_id + operation + key`; resposta concluída é reproduzida sem repetir o efeito.

Aplicado nesta release a análise, criação de relatório, simulação Solar e geração de cenário A.I TEC.

### Paginação

Listas migradas utilizam cursor opaco:

```json
{"items":[],"hasMore":false,"nextCursor":null}
```

### Jobs/SSE

`GET /api/v1/events/jobs/{id}` retorna `text/event-stream` e finaliza ao chegar a estado terminal.

## GraphQL

Endpoint `/graphql` para composição do app. Queries v14:

- `health`
- `modules`
- `entitlements`
- `properties`
- `developments`
- `comparables`
- `sourceCoverage`
- `analysisFindings`

Resolvers privados aplicam o mesmo tenant context usado pelo REST; GraphQL não é bypass do RLS.

## Eventos

NATS JetStream é alimentado por transactional outbox. Consumidores devem ser idempotentes e usar o `id` do envelope como chave de deduplicação.
