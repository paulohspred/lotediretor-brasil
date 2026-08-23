# Validation — v19-rc.3

Data da consolidação: 2026-08-23.

## Gates executados neste ambiente

**Resultado do full gate local: PASS.** O `validate-v19-rc3.sh` mantém a superfície de regressão histórica e adiciona contratos RC3. São cobertos: Solar domain/layout; A.I TEC domain/constraints/Site Solver/parking/access-lock-branch/program-terrain-building; conectores e source readiness; renderers; territorial/spatial; Property 360; RE Rural; Condomínio; AI Core/evals/Knowledge Plane/registry/high-risk/bitemporal; São Paulo lab/publication/inspection tooling; legal structure/conditions/conflicts; Python compile; JSON/YAML; TS/TSX syntax parse; shell syntax; version/runtime drift; topology estática das migrations e drift de CI/release/UI.

A suíte RC3 verifica, entre outros pontos, que alternativas A.I TEC inválidas por restrição dura não são promovidas como válidas, footprints travados permanecem invariantes no branch, ausência de acesso explícito não é inventada, unit mix mínimo pode falhar de forma explícita, cut/fill exige amostras e o Solar elétrico retorna `REQUIRES_INPUT` quando falta datasheet.

## Teste de fonte São Paulo

Foi corrigido um defeito operacional: `inspect-wfs` importava `psycopg` e exigia `PLATFORM_DATABASE_URL` mesmo quando só precisava inspecionar HTTP/WFS. A RC3 faz lazy-load do DB apenas para comandos que escrevem no banco. O teste offline de inspeção passa.

A tentativa de inspeção WFS real neste ambiente falhou depois dessa correção por indisponibilidade de resolução DNS externa para o host do GeoSampa. Isso é registrado como **não executado ao vivo**, não como PASS nem como falha do contrato de dados.

## Não executado / não homologado

- geração do `package-lock.json`: `npm install --package-lock-only` foi tentado anteriormente e excedeu o tempo/rede do ambiente; nenhum lockfile foi fabricado;
- `npm ci`, typecheck e builds com dependências reais;
- migrations 193–196 aplicadas em PostgreSQL/PostGIS real;
- RLS/cross-tenant em runtime;
- Docker Compose E2E (Docker indisponível neste ambiente);
- OpenSearch + embeddings/model provider/reranker reais;
- ingestão/promoção GeoSampa ao vivo e golden lots humanos;
- browser E2E/acessibilidade;
- staging/load/pentest/canary/backup-restore/DR.

`productionHomologated = false` até esses gates terem evidência operacional.
