# V20 Acceptance Matrix

Baseline: `8802b27878d0a745dcc9290a4de2ae564265964b` (`develop`, 2026-08-25).

A matriz impede que existência de código seja confundida com homologação. Cada frente deve ser avaliada em quatro dimensões: **implementação**, **CI/regressão**, **runtime/integração** e **fonte externa/profissional/produção**.

| Frente | Implementação | CI/regressão | Runtime/integração | Externo/profissional | Estado atual |
|---|---|---|---|---|---|
| Runtime reproduzível | Implementado | PASS | PASS | produção separada | local gate concluído |
| PostgreSQL/PostGIS + RLS | Implementado | PASS | PASS | produção separada | local gate concluído |
| OpenSearch evidence plane | Implementado | PASS | PASS | provider externo separado | local gate concluído |
| AI index lifecycle + reranker | Implementado | PASS | PASS com stack local | provider/model quality pendente | implementação/runtime local concluídos |
| Core Territorial/Legal | Fundação + golden corpus implementados | PASS | coberto pelo stack/app; casos golden sintéticos | fonte real + revisão profissional pendentes | aprofundamento real-source pendente |
| São Paulo | tooling de inspection/sync/preflight/publication/golden gate implementado | PASS estático | live não homologado | 10–20 golden lots + revisão pendentes | prioridade imediata |
| A.I TEC | núcleo preliminar implementado | regressões existentes | runtime de serviços sobe | engenharia/CAD-BIM profissional pendentes | implementação avançada pendente |
| Solar 360 | elétrico preliminar implementado | regressões existentes | runtime de serviços sobe | imagery/DSM/tarifa/grid/calibração pendentes | implementação avançada pendente |
| Imóvel 360 / RE Rural | base existente | regressões existentes | não representa fechamento do Blueprint | fontes/modelos profissionais pendentes | profundidade pendente |
| Condomínio 360 | base existente | regressões existentes | não representa fechamento do Blueprint | jurídico/documental avançado pendente | profundidade pendente |
| Prefeitura | fundação parcial | cobertura histórica | não homologado | integrações institucionais pendentes | pendente |
| Admin SaaS | fundação parcial | cobertura histórica | não homologado | billing/fiscal/ops pendentes | pendente |
| Municipality Factory | tooling parcial | cobertura parcial | live por município não homologado | fontes/licenças/goldens por município | pendente |
| Browser/mobile/a11y | não fechado | — | — | requerido | pendente |
| Segurança/load/canary | não fechado | — | — | requerido | pendente |
| Observabilidade/SLO | stack possui componentes, gate não fechado | — | parcial | operação requerida | pendente |
| HA/DR produção | scripts locais existem | backup drill PASS local | restore drill PASS local | RPO/RTO/DR produção requeridos | pendente |
| Branch protection `main` | configuração administrativa | — | — | `protected=false` observado | pendente #21 |

## Evidência runtime consolidada

- PR #34 → merge `71287ffde8590c89fcfb570c040a7f215892ac69`;
- `ci` run `32839748000` → PASS;
- `runtime-e2e` run `32839747999` → PASS;
- PR #43 → merge `8802b27878d0a745dcc9290a4de2ae564265964b`;
- `ci` run `32840808815` → PASS;
- `runtime-e2e` run `32840808863` → PASS.

Os runtimes acima comprovam stack local/reproduzível, migrations, smoke, RLS, OpenSearch ingest/retrieval isolation e backup/restore. Eles **não** comprovam produção, fonte municipal oficial, provider externo de IA, revisão jurídica/engenharia/arquitetura ou DR de produção.

## Regra de conclusão

Uma frente só pode ser marcada como homologada quando seus gates aplicáveis estiverem acompanhados de evidência reproduzível. `productionHomologated = true` exige, no mínimo, fechamento dos gates de produção definidos no issue #13 e das fontes/revisões profissionais aplicáveis.
