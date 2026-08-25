# Validation — v20 development

Data da consolidação: 2026-08-25.

Esta evidência usa quatro estados independentes: implementação, validação estática/CI, validação runtime e homologação externa/profissional. Código existente ou fixture sintética não constitui homologação. `productionHomologated = false`.

## Validação estática e CI comprovadas

A superfície histórica `validate-v19-rc3.sh` continua obrigatória durante o desenvolvimento v20. GitHub Actions executa `npm ci` com lockfile real, regressões RC3, validators incrementais v20, typecheck, builds e validação dos modelos Compose. O PR #41, que adicionou o corpus golden Core/Legal v20, passou o CI completo e foi mergeado em `develop`.

O corpus Core/Legal é explicitamente sintético e testa comportamento do engine: `PERMITTED`, `PROHIBITED`, `UNKNOWN`, conflito, vigência temporal, recuo dependente de altura, CEPAC, TDC e bloqueio de regra `CANDIDATE` como se fosse confirmada. Ele prova regressão determinística; não prova legislação de um município.

## Runtime comprovado parcialmente

O gate Docker full-stack do PR #34 já demonstrou em execução anterior:

- build das imagens de aplicação;
- subida do Compose e health dos serviços;
- migrations em PostgreSQL/PostGIS real;
- smoke de gateway/APIs/AI/Solar/A.I TEC;
- isolamento RLS cross-tenant usando role de aplicação não-owner;
- OpenSearch real alcançando estado de cluster saudável.

A etapa seguinte não chegou a executar seu primeiro comando porque `ops/ai/runtime-integration.sh` foi criado com modo Git `100644` e era chamado como executável pelo workflow. O modo foi corrigido para `100755` no commit `a25ada7b4482c0893eb6abfbc98261ba1ba95166`. O run atual do PR #34 precisa terminar verde antes de registrar ingest/retrieval e backup/restore como PASS.

## AI lifecycle/evals em validação

O PR #42 adiciona schema versionado do índice, fingerprint do espaço vetorial por modelo/revisão/dimensão, recusa de mistura incompatível, rebuild/requeue explícito e golden evaluation do reranker real. A refatoração mantém contratos RC3 de mapping como guards executáveis; o PR permanece bloqueado para merge enquanto qualquer CI estiver vermelho.

## São Paulo ao vivo

A inspeção WFS foi desacoplada do banco, mas a tentativa externa anterior encontrou indisponibilidade de DNS/rede para o GeoSampa. Não há ingestão live homologada por essa evidência. Permanecem necessários sync real, CRS/provenance, QA, promoção canônica e 10–20 golden lots revisados por profissional.

## Gates não homologados

Continuam pendentes: providers externos de IA e sua qualidade/custo; fontes oficiais/licenciadas live; browser/mobile/a11y; produção-like staging; DNS/TLS/secrets/cloud IAM; pentest e red-team operacional; load/soak/capacity; observabilidade/SLO/runbooks; canary/rollback; produção backup/restore e DR com RPO/RTO; LGPD; revisão profissional aplicável; e branch protection de `main` (#21), observada como `protected=false` em 2026-08-25.

A matriz detalhada está em `docs/V20_ACCEPTANCE_MATRIX.md`.
