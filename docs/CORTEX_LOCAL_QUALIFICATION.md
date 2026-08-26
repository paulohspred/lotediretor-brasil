# Cortex — qualificação local final por Docker

Objetivo: entregar ao Cortex um repositório que possa ser clonado e qualificado sem depender de Node, browsers, k6, PostgreSQL, OpenSearch ou observability stack instalados no host. O host precisa de **Docker Engine + Docker Compose v2**, Bash, `curl` e Python 3 para os scripts de controle.

> Este fluxo comprova o comportamento do ambiente Docker local. Ele não transforma testes locais em pentest independente, homologação de fonte externa, aprovação profissional, staging cloud real, canary real ou DR de produção.

## Desenvolvimento local simples

`docker-compose.override.yml` é carregado automaticamente por `docker compose` quando `docker-compose.yml` é usado sem `-f` explícito e adiciona o `aitec-worker`, portanto jobs persistidos não ficam sem consumidor no fluxo de desenvolvimento padrão.

```bash
docker compose up -d --build
docker compose ps
```

CI/Cortex/produção usam overlays explícitos e não dependem do override local.

## Execução principal do Cortex

Na raiz do repositório:

```bash
bash ops/cortex/qualify-local.sh ci
```

O harness usa `docker-compose.yml`, `docker-compose.ci.yml` e `docker-compose.ops.yml`, sobe profiles `full,ops` e registra cada gate em `gate-status.tsv` com `PASS/FAIL/SKIPPED`, timestamps e duração.

A sequência obrigatória inclui:

1. production parity;
2. staging parity estrutural;
3. release por digest e rollback self-test;
4. Compose/build;
5. Trivy filesystem + imagens locais para vulnerabilidades, misconfiguration e secrets;
6. health/smoke;
7. A.I TEC engine + fila persistida/worker;
8. isolamento RLS cross-tenant;
9. privacy/LGPD, legal hold e retenção;
10. Municipality Factory guards/RLS;
11. OpenSearch + AI tenant/public/temporal isolation;
12. AI red-team determinístico local;
13. fixtures sintéticos explicitamente não-oficiais;
14. browser real com Keycloak/OIDC, desktop/mobile e axe WCAG A/AA;
15. jornadas `análise → relatório`, `billing → entitlement`, `condo upload → chat` e `A.I TEC job`;
16. security baseline + supply-chain inventory + CycloneDX SBOM;
17. k6 multi-serviço;
18. fault injection e recuperação, inclusive retry/backoff da fila A.I TEC;
19. Prometheus/Grafana/Loki/Tempo/Promtail/Alertmanager/OTel;
20. backup + restore de PostgreSQL e object storage;
21. RPO/RTO sintéticos locais;
22. relatório final + manifesto SHA-256 das evidências.

Os artefatos ficam em `runtime-artifacts/cortex/<timestamp UTC>/`.

## Perfis de carga

```bash
bash ops/cortex/qualify-local.sh ci
bash ops/cortex/qualify-local.sh soak
bash ops/cortex/qualify-local.sh capacity
```

`ci` serve para regressão curta. `soak` mantém carga prolongada e `capacity` aumenta concorrência. Os thresholds são candidatos de engenharia de pré-produção e precisam ser recalibrados no staging real antes da homologação.

## Segurança, supply-chain e vulnerabilidades

O security baseline obrigatório valida headers/correlation IDs, cookies OIDC, sanitização de `returnTo`, rejeição de sessão falsa, autorização de privacy, token M2M da IA, CORS e método TRACE.

`ops/security/supply-chain.py` renderiza o candidato production+release, rejeita tags flutuantes, exige `@sha256` para artefatos próprios e gera:

- `security/supply-chain.json`;
- `security/sbom.cdx.json` em CycloneDX 1.5.

`ops/security/trivy-scan.sh` usa **Trivy 0.73.0** e bloqueia findings **HIGH/CRITICAL** corrigíveis no filesystem/dependências/misconfiguration/secrets. No Cortex, o mesmo gate também escaneia as imagens locais já construídas e preserva os resultados em `security/trivy-*.json`.

Por padrão `CORTEX_TRIVY=1` e `TRIVY_PULL=1`; o harness pode baixar explicitamente a imagem versionada do scanner. Para investigação sem rede é possível executar `CORTEX_TRIVY=0`, mas essa execução será registrada como `SKIPPED` e **não poderá** produzir qualificação local final `PASS`.

SBOM + Trivy automatizado não substituem:

- pentest independente autorizado;
- assinatura de imagem no registry;
- verificação de provenance/build attestations;
- políticas finais de CVE do ambiente de produção;
- red-team do provider de IA efetivamente configurado.

### OWASP ZAP opcional

Quando a imagem ZAP estiver disponível localmente:

```bash
CORTEX_ZAP=1 ZAP_IMAGE=ghcr.io/zaproxy/zaproxy:stable \
  bash ops/cortex/qualify-local.sh ci
```

Para permitir pull explícito:

```bash
CORTEX_ZAP=1 ZAP_PULL=1 bash ops/cortex/qualify-local.sh ci
```

O wrapper bloqueia alertas de risco alto e preserva JSON/HTML/Markdown. Continua sendo DAST automatizado de baseline, não pentest independente.

## Privacy/LGPD

A qualificação prova que pedidos do titular são tenant-scoped; `ERASURE` exige verificação/aprovação; legal hold bloqueia execução; `AUDIT_TRAIL`, `LEGAL_EVIDENCE` e `SOURCE_PROVENANCE` permanecem protegidos; eventos de privacidade são append-only; e a exclusão aprovada remove membership e só anonimiza o perfil quando não restam memberships compartilhadas. Sessões locais são revogadas após execução.

Dados de identity provider ou integrações externas continuam exigindo processo do sistema responsável; o harness não os declara apagados sem evidência.

## Fault injection e recuperação

`ops/resilience/runtime-fault-injection.sh` provoca falhas abruptas e exige recuperação observável. OpenSearch indisponível precisa resultar em 5xx ou degradação explícita sem evidência inventada. A fila A.I TEC usa `next_attempt_at` e backoff persistente; o drill exige que o mesmo `job_id` sobreviva à indisponibilidade transitória e finalize sem conclusão duplicada.

Para investigação pontual é possível pular fault injection:

```bash
CORTEX_FAULT_INJECTION=0 bash ops/cortex/qualify-local.sh ci
```

Uma execução assim **não** pode ser aceita como qualificação local final; o relatório rejeita o PASS nominal.

## Backup/restore e DR local

O backup inclui PostgreSQL platform/control e object storage. `METADATA.txt` faz parte do manifesto SHA-256. O restore usa bancos e bucket temporários, valida contratos críticos de schema, restaura objetos e compara checksums.

O drill produz `dr/dr-<stamp>.json` com RPO/RTO **sintéticos locais** e a classificação:

`LOCAL_SYNTHETIC_DR_EVIDENCE_NOT_PRODUCTION_HOMOLOGATION`

Isso não substitui PITR/failover/HA/DR no ambiente final.

## Comportamento em falha

Por padrão a stack fica rodando para inspeção imediata. Para desmontagem automática:

```bash
CORTEX_KEEP_STACK=0 bash ops/cortex/qualify-local.sh ci
```

Para preservar volumes de execução anterior:

```bash
CORTEX_RESET=0 bash ops/cortex/qualify-local.sh ci
```

A qualificação final deve usar o default `CORTEX_RESET=1`, provando boot/migrations em volumes limpos.

## Inspeção depois de falha

```bash
docker compose ps -a
docker compose logs --no-color --timestamps <service>
bash ops/privacy/runtime-integration.sh
bash ops/security/runtime-baseline.sh
TRIVY_PULL=1 TRIVY_SCAN_IMAGES=1 bash ops/security/trivy-scan.sh
bash ops/security/ai-redteam-runtime.sh
bash ops/browser/run-e2e.sh
bash ops/ai/runtime-integration.sh
bash ops/resilience/runtime-fault-injection.sh
bash ops/observability/runtime-gate.sh
LOAD_PROFILE=ci bash ops/load/run.sh
```

Interfaces locais default:

- gateway: `http://127.0.0.1:8080`;
- Keycloak: `http://127.0.0.1:8081`;
- Prometheus: `http://127.0.0.1:9090`;
- Grafana: `http://127.0.0.1:3005`.

Credenciais/secrets do harness são fixtures locais e nunca devem ser promovidos para staging/produção.

## Browser E2E

O browser roda no container oficial Playwright. O fluxo autentica realmente contra o Keycloak local, valida `ld_session` HttpOnly e percorre Client/Admin. Falhas preservam JSON, trace, screenshot e vídeo.

O runner usa `--network host`; a referência é Docker Engine em Linux. Em Docker Desktop, use suporte equivalente ou VM/runner Linux para manter paridade com CI.

## Evidência final

Uma execução gera:

- `gate-status.tsv` — ledger de cada gate;
- `qualification-report.json` e `.md` — decisão local e gates externos ainda não homologados;
- `evidence-manifest.json` — commit, dirty state, imagens e SHA-256/tamanho dos artefatos;
- `security/supply-chain.json` + `security/sbom.cdx.json`;
- `security/trivy-result.json`, `trivy-fs.json`, `trivy-fs-all.json` e scans das imagens locais;
- Playwright/k6/security/observability/AI/DR artifacts.

O relatório só aceita `localQualificationStatus=PASS` quando todos os gates locais obrigatórios e artefatos esperados estão presentes e verdes. `productionHomologated` é sempre `false` nessa qualificação.

## Bugs encontrados pelo Cortex

Não aceitar como correção:

- desabilitar RLS ou usar role owner no tráfego normal;
- remover filtros tenant/public/temporal da IA;
- transformar `CANDIDATE` em `CONFIRMED` sem revisão;
- apagar audit/legal/provenance para satisfazer erasure;
- ignorar legal hold;
- inventar dado/provider ausente;
- desativar axe/load/security/Trivy/fault-injection/health para obter PASS;
- marcar `productionHomologated=true` sem os gates externos do issue #13.

Após cada correção, execute primeiro o gate específico e depois `bash ops/cortex/qualify-local.sh ci`. Antes do handoff final, execute também `soak` e `capacity` em máquina adequada.

## Critério de handoff

O código está pronto para o ciclo final do Cortex quando CI, `security-scan` e runtime-e2e do PR executarem steps reais e ficarem verdes, e o harness local `ci` reproduzir PASS com relatório/evidências completos. Depois, Cortex executa `soak`, `capacity`, ZAP quando disponível, exploração visual/manual e fault cases adicionais.

Continuam externos: pentest independente, cloud/staging real, secrets/IAM/DNS/TLS/registry reais, assinatura/provenance de imagens, canary/rollback real, HA/PITR/DR de produção, fontes/licenças/providers oficiais, revisões profissionais/institucionais e proteção administrativa da `main`.
