# V20 Acceptance Matrix

Baseline runtime validado: `42ac9a13ccb726f68e48a62be75e7d5bec1ffaa7` (`develop`, 2026-08-26; merge do PR #66).

A matriz impede que existência de código seja confundida com homologação. Cada frente é avaliada em quatro dimensões: **implementação**, **CI/regressão**, **runtime/integração** e **fonte externa/profissional/produção**.

| Frente | Implementação | CI/regressão | Runtime/integração | Externo/profissional | Estado atual |
|---|---|---|---|---|---|
| Runtime reproduzível | Implementado | PASS #456 | PASS #60 | produção separada | gate local concluído |
| PostgreSQL/PostGIS + RLS | Implementado | PASS | PASS #60 | produção separada | gate local concluído |
| OpenSearch evidence plane | Implementado; `indexed_at` só após `refresh=wait_for` | PASS | PASS #60, tenant/public/temporal | provider externo separado | gate local concluído |
| AI index lifecycle + reranker | Implementado | PASS | PASS com stack local | provider/model quality pendente | implementação/runtime local concluídos |
| Core Territorial/Legal | Engine temporal + golden corpus + instrumentos determinísticos implementados | PASS | coberto pelo stack/app; goldens sintéticos | fonte real + revisão profissional pendentes | aprofundamento real-source pendente |
| São Paulo | inspection/sync/preflight/publication/golden gate implementados | PASS estático | tooling disponível; live não homologado | fonte oficial + 10–20 golden lots + revisão | prioridade de dados reais |
| A.I TEC | terrain/TIN, road engineering, basement parking, Building/Unit/Room Solver, environment, finance, Pareto/optimization e exports implementados | PASS | advanced runtime API PASS #60 | dados de terreno/CAD-BIM/licenças/revisão profissional | engine avançado; homologação profissional pendente |
| Solar | cenário v20 + string/MPPT e cálculos determinísticos implementados | PASS | smoke/runtime de serviço | imagery/DSM/DEM, tarifa/grid/equipamentos/calibração/revisão | engine implementado parcialmente contra dados externos |
| Imóvel 360 / RE Rural | camada operacional v20 de mercado/readiness + base histórica | PASS | runtime de plataforma | fontes oficiais/licenciadas, modelos e casos profissionais | código-base avançado; dados reais pendentes |
| Condomínio 360 | governança/lifecycle operacional v20 + base documental | PASS | runtime de plataforma | documentos reais, revisão jurídica e fluxos finais | código operacional; produto/E2E pendentes |
| Prefeitura | onboarding, datasets, publicação/rollback, CTM/CIB-SINTER/PGV/IPTU/ITBI/licenciamento, open data, recálculo, export/offboarding implementados | PASS | DB/RLS/runtime cobertos | integrações e homologação institucional | código operacional concluído, instituição externa pendente |
| Admin SaaS | billing/ledger/dunning/refund/chargeback, fiscal orchestration, support, CMS, analytics, AI Ops e release/rollback implementados | PASS | control-plane RLS/runtime cobertos | Mercado Pago/NFS-e/produção e operação real | código operacional avançado |
| Municipality Factory | connector contracts, discovery seguro, snapshots, QA, candidates, goldens, publication, monitoramento e cobertura implementados | PASS | DB guards/RLS PASS #60 | fontes/licenças/goldens reais por município | implementação local concluída pelo #66 |
| Browser/mobile/a11y | não fechado | — | — | revisão requerida | pendente #13 |
| Segurança operacional | guards/RLS/red-team sintético e production gate existentes | regressões parciais | runtime isolamento PASS | pentest independente + exercícios operacionais | parcial #13 |
| Load/soak/capacity | k6 health smoke existente | básico | não fecha capacidade por serviço | ambiente alvo requerido | pendente #13 |
| Observabilidade/SLO | OTel/Prometheus/Grafana/Tempo/Loki e schemas operacionais existem | parcial | stack configurada | SLO/alert/runbook e evidência operacional | pendente #13 |
| Backup/restore | scripts e dashboard operacional implementados | PASS | restore drill PASS #60 | produção/PITR/DR ainda requeridos | gate local concluído |
| HA/DR produção | guardrails/scripts locais | parcial | restore local comprovado | RPO/RTO/HA/DR medidos no alvo | pendente #13 |
| Staging/IaC/canary | compose production e release controls existem | parcial | não homologado | cloud/IAM/DNS/TLS/canary real | pendente #13 |
| LGPD operacional | políticas/guards de dados existem em vários domínios | parcial | não há drill final consolidado | DPO/política/retenção real | pendente #13 |
| Branch protection `main` | configuração administrativa | — | `protected=false` observado | ação administrativa GitHub | pendente #21 |

## Evidência runtime consolidada

- PR #34 → merge `71287ffde8590c89fcfb570c040a7f215892ac69`; `ci` 32839748000 PASS; `runtime-e2e` 32839747999 PASS.
- PR #43 → merge `8802b27878d0a745dcc9290a4de2ae564265964b`; `ci` 32840808815 PASS; `runtime-e2e` 32840808863 PASS.
- PR #66 → merge `42ac9a13ccb726f68e48a62be75e7d5bec1ffaa7`; `ci` run #456 PASS; `runtime-e2e` run #60 PASS; artifact `9602867789`.

O runtime #60 prova stack local/reproduzível, migrations, smoke, A.I TEC advanced API, RLS, Municipality Factory guards, OpenSearch ingest/retrieval tenant/public/temporal isolation e backup/restore. Ele **não** prova produção, fonte municipal oficial, provider externo de IA, revisão jurídica/engenharia/arquitetura/fiscal ou DR de produção.

## Regra de conclusão

Uma frente só pode ser marcada como homologada quando seus gates aplicáveis estiverem acompanhados de evidência reproduzível. `productionHomologated = true` exige, no mínimo, fechamento dos gates de produção do issue #13 e das fontes/revisões profissionais aplicáveis.
