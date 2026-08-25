# Status — v20 development

## Estado atual

O repositório está em desenvolvimento v20 sobre o runtime versionado `19.0.0-rc.3`, preservando toda a superfície de regressão RC3 enquanto os contratos v20 são aprofundados. **Implementação, CI, runtime, dados reais e homologação profissional/produção são gates separados.** `productionHomologated = false`.

## Evidência já obtida

- `package-lock.json`, `npm ci`, typecheck e builds são executados de forma reproduzível no GitHub Actions;
- Core Territorial/Legal ganhou corpus golden v20 sintético e versionado cobrindo decisão permitida/proibida/desconhecida, conflitos, temporalidade, recuo dependente de altura, CEPAC, TDC e bloqueio de regra `CANDIDATE`; o PR #41 passou CI e foi mergeado em `develop`;
- AI Core preserva Knowledge Plane, ACL/tenant, bitemporalidade, retrieval lexical/híbrido com RRF, reranker legal, registries, evidence gates e high-risk deterministic-rule gate;
- o runtime Docker full-stack já demonstrou health dos serviços, migrations PostgreSQL/PostGIS, smoke pelo gateway e isolamento RLS cross-tenant com application role não-owner;
- OpenSearch real já demonstrou cluster health no gate de runtime;
- São Paulo preserva contratos de lote/zona, publicação por dataset, promoção canônica e inspeção WFS desacoplada do banco;
- A.I TEC preserva Site Solver, parking, acesso explícito, locks/branch/regenerate, unit mix, cut/fill conceitual, Building Stack, análises e exports;
- Solar preserva o design elétrico preliminar string/MPPT somente com dados explícitos.

## Fechamentos em andamento

O PR #34 executa o gate Docker E2E completo. A causa da falha anterior do passo AI/OpenSearch foi identificada: `ops/ai/runtime-integration.sh` havia sido adicionado com modo Git `100644`, embora o workflow o executasse diretamente. O modo foi corrigido para `100755`; o novo run deve provar ingest/retrieval e então alcançar o drill de backup/restore. Isso ainda não é registrado como PASS até o run terminar verde.

O PR #42 implementa lifecycle reproduzível do índice de evidências: schema versionado, fingerprint de espaço vetorial por modelo/revisão/dimensão, recusa de índice incompatível, rebuild/requeue explícito e golden eval do reranker real. A compatibilidade RC3 permanece obrigatória e está sendo validada pelo CI antes de qualquer merge.

## São Paulo e fontes reais

Nenhum dado municipal deve ser marcado como oficial ou homologado a partir de fixtures sintéticas. Continuam pendentes: acesso live ao GeoSampa, sync com CRS/provenance, QA, promoção canônica e 10–20 golden lots revisados por profissional, além das avaliações legais temporais/citação/abstenção sobre fontes reais.

## Gates externos ainda pendentes

Permanecem fora de qualquer declaração de produção: providers externos de IA avaliados; browser/mobile/a11y; pentest e red-team operacional; load/soak/capacity; staging production-like; DNS/TLS/secrets/cloud IAM; observabilidade/SLO/runbooks; canary/rollback; backup/restore e DR de produção com RPO/RTO; LGPD; e revisões profissional, jurídica, engenharia e arquitetura aplicáveis. A branch `main` também foi observada com `protected=false` em 2026-08-25 e requer o gate administrativo #21.

## Próxima ordem de fechamento

1. tornar PR #34 totalmente verde e integrar o runtime gate;
2. validar PR #42 sobre a base atualizada, incluindo runtime depois que o workflow estiver em `develop`;
3. atualizar evidência/trackers e encerrar apenas issues cujos critérios estejam efetivamente provados;
4. avançar São Paulo live/golden lots e os demais blocos do Blueprint v2.0 sem converter falta de fonte, credencial ou revisão humana em resultado sintético.
