# LoteDiretor v20 — matriz de aceitação

Data de consolidação: 2026-08-25.

Esta matriz separa quatro dimensões que não podem ser tratadas como equivalentes: **implementação**, **validação estática/CI**, **validação em runtime** e **homologação externa/profissional**. Existência de código não implica homologação. `productionHomologated` permanece `false` até os gates externos do Blueprint Final v2.0 serem comprovados.

| Frente | Implementação | CI/contratos | Runtime | Homologação externa/profissional |
| --- | --- | --- | --- | --- |
| Core Territorial + Legal/Rule Engine | Implementado e aprofundado; corpus golden v20 sintético incorporado | PASS no PR #41 e mergeado em `develop` | depende do runtime consolidado | PENDENTE para regras/fontes municipais reais e revisão profissional |
| AI Core — retrieval/evidence plane | Knowledge Plane, ACL/tenant, temporalidade, RRF, reranker, registries e high-risk gates implementados | regressões RC3/v20 obrigatórias | gate OpenSearch/ai-ingest em validação no PR #34 | PENDENTE para providers externos, qualidade/custo e avaliação com dados reais |
| AI Core — lifecycle vetorial/evals | schema/fingerprint/rebuild/eval do reranker implementados no PR #42 | EM VALIDAÇÃO; não promover enquanto houver check vermelho | deve ser revalidado sobre o runtime consolidado | PENDENTE para embeddings/reranker externos avaliados |
| Runtime Docker | workflow full-stack, health, migrations, smoke, RLS, OpenSearch e backup/restore implementados no PR #34 | CI estático separado | EM VALIDAÇÃO no PR #34 | não equivale a produção |
| São Paulo | contratos, publicação, promoção canônica e inspeção WFS implementados | contratos offline cobertos | live WFS não homologado neste ambiente | PENDENTE: sync/QA/promoção e 10–20 golden lots humanos |
| A.I TEC | Site Solver, parking, access, locks/branch, unit mix, terrain/cut-fill conceitual, Building Stack e exports existentes | regressões RC3 | runtime específico ainda não constitui projeto executivo | PENDENTE: engenharia avançada, CAD/BIM e revisão profissional |
| Solar | domínio/layout + string/MPPT preliminar com entrada explícita | regressões RC3 | runtime específico não fecha Solar 360 | PENDENTE: imagery/DSM/shadow/tarifa/OCR/grid/estrutura/calibração |
| Imóvel 360 + RE Rural | base funcional parcial | regressões existentes | cobertura runtime parcial | PENDENTE: fontes licenciadas/oficiais, calibração e goldens profissionais |
| Condomínio 360 | base funcional parcial | regressões existentes | cobertura runtime parcial | PENDENTE: workflows avançados, integrações e revisão jurídica |
| Prefeitura/Admin/Municipality Factory | fundações parciais | cobertura contratual parcial | não homologado | PENDENTE |
| Browser/mobile/a11y | não encerrado | não encerrado | PENDENTE | PENDENTE |
| Segurança/carga/canary/HA-DR | não encerrado | não encerrado | PENDENTE | PENDENTE |
| Branch protection `main` | configuração administrativa, não código | `main` observado com `protected=false` em 2026-08-25 | n/a | PENDENTE (#21) |

## Regra para atualizar a matriz

- `PASS` exige evidência reproduzível do gate correspondente.
- `IMPLEMENTED` significa que o comportamento/documento existe e tem contrato verificável; não significa verdade municipal, parecer jurídico, projeto executivo ou homologação de produção.
- Dados sintéticos/golden fixtures nunca podem ser promovidos como fonte oficial.
- Ausência de credencial/provider externo deve permanecer explícita; fallback local não prova qualidade de provider.
- Mudanças em rule engine, retrieval, prompt/model/tool ou schema vetorial exigem regressão antes de promoção.

## Gates que bloqueiam `productionHomologated=true`

Permanecem obrigatórios, entre outros: São Paulo/demais fontes ao vivo com provenance e goldens profissionais; browser E2E/mobile/a11y; segurança/pentest/prompt-injection/tenant leakage; carga/soak/capacity; observabilidade/SLO/runbooks; staging production-like; canary/rollback; backup/restore e DR com RPO/RTO; DNS/TLS/secrets/cloud IAM; LGPD; e revisões profissionais aplicáveis.
