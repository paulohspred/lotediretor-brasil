# v14 — Fronteiras e hardening estrutural

A v14 é uma release estrutural. Ela não tenta completar novos domínios do Blueprint; corrige fundações que impediriam os módulos existentes de operar com isolamento, contratos e eventos confiáveis.

## Platform API

O bootstrap agora importa módulos explícitos:

- `CoreModule`: IAM/BFF, catálogo, Source Registry, Parcel Resolver, análise e operações-base.
- `DomainsModule`: compatibilidade funcional recuperada de Imóvel 360, Rural, Condomínio, Solar, A.I TEC e Prefeitura. O arquivo histórico `v7.controller.ts` permanece temporariamente como adaptador de recuperação e será decomposto por bounded context nas próximas releases.
- `ContractsModule`: catálogo REST e documento OpenAPI 3.1 baseline.
- `JobEventsModule`: SSE para jobs longos.
- `MetricsModule`: métricas técnicas.

A direção é migrar progressivamente o adaptador histórico para `src/modules/{iam,core,geo,legal,planning,cadastre,registry,market,property360,rural,condo,municipality,analysis,report}` sem quebrar contratos do frontend.

## Tenant context e RLS

O runtime `lotediretor_app` é non-owner e `NOBYPASSRLS`. Toda operação privada deve executar dentro de transação com:

```sql
select set_config('app.tenant_id', '<tenant uuid>', true);
```

`tenantTx()` e `tenantQuery()` são os únicos helpers aprovados para consultas REST/GraphQL/SSE em dados privados. Queries globais de catálogo/fontes podem continuar sem tenant context.

Linhas oficiais/compartilhadas com `tenant_id IS NULL` possuem políticas explícitas somente para leitura. Escritas do runtime exigem sempre o tenant atual.

## Migrations e bootstrap

A ordem limpa de inicialização é agora:

1. Platform/Control databases healthy.
2. `platform-migrate` e `control-migrate` executam todas as migrations como owners.
3. `platform-db-role-init` atribui senhas aos papéis runtime que as migrations criaram.
4. APIs, workers, Martin e Event Dispatcher iniciam usando papéis non-owner/dedicados.

Isto elimina a corrida antiga na qual o bootstrap podia tentar alterar um papel ainda inexistente.

## Workers

Workers não usam mais o owner de migrations:

- `lotediretor_worker`: processamento cross-tenant do Data Plane; non-owner/non-superuser, DML apenas, `BYPASSRLS` deliberado por ser workload interno de fila.
- `lotediretor_control_worker`: equivalente no Control Plane.
- `lotediretor_event_dispatcher`: acesso somente ao schema `event`.
- `lotediretor_tiles`: somente leitura do schema `tiles`.

## Eventos

Comandos críticos gravam eventos no `event.outbox` dentro da mesma transação do dado de negócio. O `event-dispatcher` publica no NATS JetStream e só marca `PUBLISHED` após receber ACK persistente. `msgID=outbox.id` permite deduplicação no JetStream.

Eventos já emitidos na v14 incluem:

- `source.snapshot.published`
- `analysis.completed`
- `report.queued`
- `report.completed`
- `document.queued`
- `document.processed`
- `solar.scenario.completed`
- `aitec.scenario.completed`

## Contratos transversais

- erros HTTP: `code`, `message`, `fields`, `trace_id`, `retryable`;
- `x-request-id` e `x-trace-id` em respostas;
- `Idempotency-Key` em comandos selecionados;
- cursor opaco em listas grandes já migradas;
- SSE para progresso de relatório/ingestão;
- GraphQL expandido para composição do app;
- OpenAPI 3.1 baseline em `/api/v1/openapi.json`.

## Limites conhecidos

A modularização interna ainda é parcial: `v7.controller.ts` continua grande e será decomposto na v15/v16. O OpenAPI atual é um catálogo versionado dos contratos prioritários, ainda não descreve todos os 100+ handlers. O runtime Docker/staging não foi homologado neste ambiente.
