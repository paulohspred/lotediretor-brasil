# Cortex — qualificação local final por Docker

Objetivo: entregar ao Cortex um repositório que possa ser clonado e qualificado sem depender de Node, Python, browsers, k6, PostgreSQL, OpenSearch ou observability stack instalados no host. O host precisa de **Docker Engine + Docker Compose v2**, shell POSIX/Bash e Python 3 para os scripts de controle.

> Este fluxo comprova o comportamento do ambiente Docker local. Ele não transforma testes locais em pentest, homologação de fonte externa, aprovação profissional, staging production-like ou DR de produção.

## Execução principal

Na raiz do repositório:

```bash
bash ops/cortex/qualify-local.sh ci
```

O comando usa `docker-compose.yml`, `docker-compose.ci.yml` e `docker-compose.ops.yml`, sobe profiles `full,ops` e executa em sequência:

1. validação do modelo Compose e build limpo das imagens;
2. health/migrations/smoke do gateway e serviços;
3. A.I TEC v20 runtime;
4. isolamento RLS cross-tenant;
5. guards/RLS da Municipality Factory;
6. OpenSearch + AI ingest/retrieval com isolamento tenant/public/temporal;
7. browser real com OIDC/Keycloak, client, admin, mobile e axe WCAG A/AA;
8. observabilidade Prometheus/Grafana/Loki/Tempo/Promtail/Alertmanager/OTel;
9. carga k6 multi-serviço;
10. backup + restore drill.

Os artefatos ficam em `runtime-artifacts/cortex/<timestamp UTC>/`.

## Perfis de carga

```bash
bash ops/cortex/qualify-local.sh ci
bash ops/cortex/qualify-local.sh soak
bash ops/cortex/qualify-local.sh capacity
```

`ci` é curto e serve para regressão. `soak` mantém 25 VUs por 10 minutos. `capacity` cresce até 75 VUs. Os thresholds atuais são gate de engenharia de pré-produção: erros <1%, checks >99%, p95 <1,5 s e p99 <3 s. Esses números devem ser recalibrados com dados do staging real antes da homologação.

## Comportamento em falha

Por padrão a stack **fica rodando** para permitir inspeção imediata pelo Cortex. O script imprime os caminhos dos artefatos e endpoints locais. Para desmontar automaticamente:

```bash
CORTEX_KEEP_STACK=0 bash ops/cortex/qualify-local.sh ci
```

Para preservar volumes de uma execução anterior:

```bash
CORTEX_RESET=0 bash ops/cortex/qualify-local.sh ci
```

O default é `CORTEX_RESET=1`, porque a qualificação reproduzível deve provar boot/migrations em volumes limpos.

## Inspeção depois de uma falha

Com a stack preservada:

```bash
docker compose ps -a
docker compose logs --no-color --timestamps <service>
bash ops/browser/run-e2e.sh
bash ops/ai/runtime-integration.sh
bash ops/observability/runtime-gate.sh
LOAD_PROFILE=ci bash ops/load/run.sh
```

Interfaces locais default:

- aplicação/gateway: `http://127.0.0.1:8080`;
- Keycloak: `http://127.0.0.1:8081`;
- Prometheus: `http://127.0.0.1:9090`;
- Grafana: `http://127.0.0.1:3005`.

Credenciais e secrets definidos pelo harness são **fixtures locais**. Não devem ser promovidos para staging/produção.

## Browser E2E

O browser é executado no container oficial Playwright. O fluxo autentica de verdade contra o Keycloak local, valida a criação de `ld_session` HttpOnly e percorre os workspaces Client/Admin. Falhas preservam JSON, trace, screenshot e vídeo em `runtime-artifacts/.../browser`.

O runner usa `--network host`, portanto o caminho de referência é Docker Engine em Linux. Em Docker Desktop, habilitar suporte equivalente a host networking ou executar o Cortex em VM/runner Linux para manter a mesma topologia do CI.

## Bugs encontrados pelo Cortex

Correções devem manter os invariantes de segurança já provados. Em particular, não aceitar como “fix”:

- desabilitar RLS ou usar role owner para tráfego normal;
- remover filtros tenant/public/temporal no AI retrieval;
- transformar regra `CANDIDATE` em `CONFIRMED` sem revisão;
- inventar dado de fonte/provider ausente;
- desativar axe/load/health para fazer o gate passar;
- marcar `productionHomologated=true` sem os gates externos do issue #13.

Após cada correção, executar primeiro o gate específico e depois `bash ops/cortex/qualify-local.sh ci`. Antes do handoff final, executar também `soak` e `capacity` em máquina com recursos suficientes.

## Critério de handoff para testes finais

O repositório está pronto para o ciclo final do Cortex quando CI + runtime-e2e do PR estiverem verdes e o harness local `ci` reproduzir o mesmo resultado. O Cortex então deve usar `soak/capacity`, exploração visual/manual e fault injection local para encontrar bugs residuais. Pentest independente, fontes/credenciais oficiais, staging real, canary/rollback real e DR com RPO/RTO medidos continuam depois desse fechamento de código.
