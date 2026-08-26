# V20 Acceptance Matrix

Baseline runtime consolidado em `develop`: `42ac9a13ccb726f68e48a62be75e7d5bec1ffaa7` (PR #66), com CI #456 e runtime-e2e #60 PASS.

O PR #68 concentra a qualificação v20 pré-Cortex. O código/gates abaixo podem estar **implementados** sem ainda estarem **validados no head atual**, porque os GitHub-hosted jobs recentes têm terminado com `runner_id=0` e `steps=[]`. Nenhum desses runs é contado como PASS.

`productionHomologated=false` permanece obrigatório.

| Frente | Implementação | CI/regressão | Runtime/integração | Externo/profissional | Estado atual |
|---|---|---|---|---|---|
| Runtime reproduzível | Compose full/ops + harness Cortex | static contracts no #68; runner real pendente | #60 PASS; novo harness pendente de execução integral | produção separada | capacidade pronta; revalidação do head necessária |
| PostgreSQL/PostGIS + RLS | Implementado + cross-tenant runtime scripts | contratos presentes | #60 PASS e suíte ampliada inclui `aitec.job` | produção separada | local consolidado; novo head a revalidar |
| OpenSearch evidence plane | `refresh=wait_for`, ACL/public/temporal, provenance | regressões existentes | #60 PASS; fault recovery e load ampliados no #68 | segurança/cluster final dependem do ambiente | local avançado |
| AI Core | hybrid retrieval/RRF/rerank, bitemporal, high-risk, red-team, RED/OTLP | regressões estáticas/unitárias | retrieval isolation/fault/load codificados | provider/model quality/cost real | código local avançado |
| Core Territorial/Legal | evaluator temporal, instrumentos, analysis/evidence/report | regressões v20 | jornada UI análise→relatório adicionada | fonte real + revisão profissional | código/jornada principal avançados |
| São Paulo | inspection/sync/preflight/publication/golden tooling | regressões | tooling local | GeoSampa live + goldens humanos | dados reais prioritários |
| Imóvel 360 | ficha, mercado, CRM, diligence, AVM/comparables contracts, report | regressões + UI contract | UI resolve→analysis→report no #68 | comparáveis/licenças/calibração real | código avançado; dados reais pendentes |
| RE Rural | registry/identity/geometry/overlap/monitor/export/readiness | regressões | plataforma local | CAR/SIGEF/SNCR/CCIR/CIB/CAFIR/IBAMA/INPE/FUNAI/CNUC/SICOR reais | fontes/goldens pendentes |
| Condomínio 360 | docs/rules/governança/unidades/obras/assembleias/manutenção/compliance/AI | regressões + UI contract | UI private upload→index→chat no #68 | documentos/OCR/revisão jurídica/providers reais | produto local avançado |
| Solar | posição solar, POA, packing, string/MPPT, battery/tariff/grid/finance | regressões numéricas | runtime/load codificados | imagery/DSM/DEM/tarifa/equipamentos/BDGD/calibração | engine local avançado |
| A.I TEC | solver avançado + `aitec.job` + worker/retry/backoff/metrics | unit/contract/UI regressions | UI job→worker→resultado, RLS/fault/load codificados | CAD/BIM/datasets/licenças/revisão/goldens | engine/job/UX crítica avançados |
| Prefeitura | onboarding/datasets/publication/fiscal/open-data/export | regressões | DB/RLS/runtime local | municípios/Receita/SINTER/CIB reais | integração institucional pendente |
| Admin SaaS | billing/ledger/fiscal/support/CMS/analytics/AI Ops/release + BillingWorkspace | regressões + UI contract | UI subscription→invoice→payment→entitlement no #68 | Mercado Pago/NFS-e/operação real | código operacional avançado |
| Municipality Factory | connectors/discovery/snapshots/QA/candidates/goldens/publication/monitor | regressões | guards/RLS #60 PASS | fontes/licenças/goldens reais | implementação local consolidada |
| Browser/mobile/a11y | Playwright OIDC real, desktop/mobile, axe, 4 jornadas críticas UI | contract estático presente | execução real do novo head pendente | exploração manual final | implementado; validação final pendente |
| Segurança operacional | RLS/auth/tenant leakage, AI red-team, baseline, fault injection, ZAP opcional, SBOM | regressões presentes | local scripts/harness | pentest independente + CVE/image-signature policies finais | automatizável avançado; pentest externo pendente |
| Load/soak/capacity | k6 `ci/soak/capacity` multi-serviço | scripts/thresholds versionados | execução prolongada pendente | staging alvo necessário | implementado; medição final pendente |
| Observabilidade/SLO | RED 5 serviços, OTLP, Prometheus/Grafana/Loki/Tempo/Alertmanager, worker queue metrics | config/rules contracts | runtime gate codificado | owner/on-call e exercício no alvo | implementado localmente; exercício final pendente |
| Backup/restore/DR local | DB + object storage + checksums + schema asserts + RPO/RTO sintéticos | DR contract test | harness codificado | PITR/failover/HA/DR real | capacidade local avançada; produção pendente |
| Staging/release/canary | production parity, structural staging parity, `image@sha256`, rollback self-test, AI-eval canary | contracts no CI | execução real pendente | cloud/IAM/secrets/DNS/TLS/registry/canary real | modelo de promoção implementado |
| Supply-chain | imagens MinIO versionadas, inventory + CycloneDX SBOM, floating-tag guards | contract presente | gera artefatos no harness | CVE scan, signatures/attestations e registry real | inventário local implementado |
| LGPD operacional | requests, retention, legal hold, erasure/export, append-only | regressões | drill DB/API no harness | DPO/políticas e sistemas externos/IdP | implementação local avançada |
| Branch protection `main` | configuração administrativa | — | `protected=false` observado | ação GitHub admin | pendente #21 |

## Evidência consolidada que já existe

- PR #34 → merge `71287ffde8590c89fcfb570c040a7f215892ac69`; CI/runtime PASS.
- PR #43 → merge `8802b27878d0a745dcc9290a4de2ae564265964b`; CI/runtime PASS.
- PR #66 → merge `42ac9a13ccb726f68e48a62be75e7d5bec1ffaa7`; CI #456 PASS; runtime-e2e #60 PASS; artifact `9602867789`.

O runtime #60 prova stack/migrations/smoke, A.I TEC advanced API, RLS, Municipality Factory, OpenSearch tenant/public/temporal isolation e backup/restore. O PR #68 amplia esse escopo, porém ainda precisa de uma execução com **steps reais** antes de ser considerado validado ou mergeado.

## Regra de conclusão

Uma frente só é homologada quando seus gates aplicáveis têm evidência reproduzível. `productionHomologated=true` exige, além do fechamento local, pentest, dados/providers/revisões aplicáveis, staging real, canary/rollback real e HA/PITR/DR com RPO/RTO no ambiente final.
