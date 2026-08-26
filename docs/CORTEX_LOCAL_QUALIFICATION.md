# Cortex — qualificação local final por Docker

Objetivo: entregar ao Cortex um repositório que possa ser clonado e qualificado sem depender de Node, browsers, k6, PostgreSQL, OpenSearch ou observability stack instalados no host. O host precisa de **Docker Engine + Docker Compose v2**, shell POSIX/Bash, `curl` e Python 3 para os scripts de controle.

> Este fluxo comprova o comportamento do ambiente Docker local. Ele não transforma testes locais em pentest independente, homologação de fonte externa, aprovação profissional, staging production-like, canary real ou DR de produção.

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
5. privacy/LGPD: RLS, pedidos do titular, legal hold, append-only e retenção protegida;
6. guards/RLS da Municipality Factory;
7. OpenSearch + AI ingest/retrieval com isolamento tenant/public/temporal;
8. browser real com OIDC/Keycloak, client, admin, mobile e axe WCAG A/AA;
9. security baseline: headers, cookies OIDC, open redirect, sessão falsa, token M2M, CORS e TRACE;
10. carga k6 multi-serviço;
11. fault injection controlado com SIGKILL de APIs e indisponibilidade/recuperação do OpenSearch;
12. observabilidade Prometheus/Grafana/Loki/Tempo/Promtail/Alertmanager/OTel após a recuperação;
13. backup + restore drill;
14. manifesto final de evidências com commit, imagens e SHA-256 dos artefatos.

Os artefatos ficam em `runtime-artifacts/cortex/<timestamp UTC>/`.

## Perfis de carga

```bash
bash ops/cortex/qualify-local.sh ci
bash ops/cortex/qualify-local.sh soak
bash ops/cortex/qualify-local.sh capacity
```

`ci` é curto e serve para regressão. `soak` mantém carga prolongada e `capacity` aumenta concorrência. Os thresholds definidos em `ops/load` são gates de engenharia de pré-produção e devem ser recalibrados com dados do staging real antes da homologação.

## Segurança dinâmica opcional — OWASP ZAP

O security baseline obrigatório não depende de internet. Quando a imagem ZAP já estiver disponível localmente, o Cortex pode acrescentar o scanner:

```bash
CORTEX_ZAP=1 ZAP_IMAGE=ghcr.io/zaproxy/zaproxy:stable \
  bash ops/cortex/qualify-local.sh ci
```

O harness não baixa imagens de scanner silenciosamente. Para permitir pull explícito:

```bash
CORTEX_ZAP=1 ZAP_PULL=1 bash ops/cortex/qualify-local.sh ci
```

O wrapper `ops/security/zap-baseline.sh` bloqueia alertas de risco alto e preserva JSON/HTML/Markdown. Isso continua sendo DAST automatizado de baseline, não substituto de pentest independente.

## Privacy/LGPD

A qualificação prova no banco e na API que:

- pedidos do titular são tenant-scoped;
- `ERASURE` exige verificação e aprovação;
- legal hold ativo bloqueia a execução;
- `AUDIT_TRAIL`, `LEGAL_EVIDENCE` e `SOURCE_PROVENANCE` não podem virar retenção destrutiva/automática;
- eventos de privacidade são append-only;
- uma exclusão aprovada remove a membership do tenant e só anonimiza o perfil compartilhado quando não restarem outras memberships;
- sessões locais do titular são revogadas após a execução.

O endpoint de exportação declara seu escopo. Dados mantidos pelo identity provider ou por integrações externas continuam exigindo processo específico do sistema responsável; não são inventados como “apagados”.

## Fault injection e recuperação

`ops/resilience/runtime-fault-injection.sh` mata abruptamente `platform-api`, `control-api` e `ai-gateway`, exige que a indisponibilidade seja visível e só aceita recuperação quando health volta a responder. Em seguida desliga o OpenSearch e exige **fail-closed**: retrieval pode retornar 5xx ou degradação explícita sem itens, mas nunca evidência como se o backend estivesse íntegro. Após o restart, a suíte completa de AI retrieval/tenant/public/temporal é executada novamente.

Para pular fault injection apenas durante investigação pontual:

```bash
CORTEX_FAULT_INJECTION=0 bash ops/cortex/qualify-local.sh ci
```

Isso não deve ser usado no handoff final.

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
bash ops/privacy/runtime-integration.sh
bash ops/security/runtime-baseline.sh
bash ops/browser/run-e2e.sh
bash ops/ai/runtime-integration.sh
bash ops/resilience/runtime-fault-injection.sh
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

## Evidência final

O arquivo `evidence-manifest.json` no diretório da execução registra o SHA do commit, estado `dirty/clean`, imagens Compose observadas e SHA-256/tamanho dos artefatos capturados. Ele serve para responder “qual código e quais evidências produziram este PASS/FAIL?” sem depender de memória operacional.

## Bugs encontrados pelo Cortex

Correções devem manter os invariantes de segurança já provados. Em particular, não aceitar como “fix”:

- desabilitar RLS ou usar role owner para tráfego normal;
- remover filtros tenant/public/temporal no AI retrieval;
- transformar regra `CANDIDATE` em `CONFIRMED` sem revisão;
- apagar audit/legal/provenance para satisfazer pedido de exclusão;
- ignorar legal hold;
- inventar dado de fonte/provider ausente;
- desativar axe/load/security/fault-injection/health para fazer o gate passar;
- marcar `productionHomologated=true` sem os gates externos do issue #13.

Após cada correção, executar primeiro o gate específico e depois `bash ops/cortex/qualify-local.sh ci`. Antes do handoff final, executar também `soak` e `capacity` em máquina com recursos suficientes.

## Critério de handoff para testes finais

O repositório está pronto para o ciclo final do Cortex quando CI + runtime-e2e do PR estiverem verdes e o harness local `ci` reproduzir o mesmo resultado, incluindo privacy, security, fault recovery, observability e backup/restore. O Cortex então deve usar `soak/capacity`, ZAP quando disponível, exploração visual/manual e falhas adicionais para encontrar bugs residuais. Pentest independente, fontes/credenciais oficiais, staging real, canary/rollback real e DR com RPO/RTO medidos continuam depois desse fechamento de código.
