# Status — v19-rc.3

## Marco atual

**Core Closure + A.I TEC Access/Branch/Program/Terrain/Building + Solar Electrical Preliminary.** A RC3 preserva a fundação territorial/jurídica e o AI Knowledge Plane anteriores e fecha o escopo técnico anunciado para esta etapa sem declarar homologação de produção.

## Implementado e coberto por testes locais

- runtime/workspaces normalizados em `19.0.0-rc.3`;
- CI e release gate apontam para `validate-v19-rc3.sh`;
- regressões históricas permanecem obrigatórias;
- A.I TEC: Site Solver, parking geométrico, acesso/road conceitual explícito, locks, branch/regenerate, unit mix, cut/fill por amostra, Building Stack, analyses e exports;
- Solar: string/MPPT preliminar somente com dados elétricos fornecidos/catálogo explícito;
- AI Core: Knowledge Plane, bitemporalidade, hybrid retrieval foundation, registry, evidence/high-risk gates;
- São Paulo: contratos lote/zona, publicação por dataset, promoção canônica e inspeção WFS desacoplada de DB;
- tenant/RLS e provenance continuam obrigatórios nas novas tabelas RC3.

## O que esta RC não afirma resolver

A.I TEC ainda não é projeto executivo e não fecha: viário de engenharia com raios de giro/emergência; garagem de subsolo/rampas/pilares; TIN/DEM real e terraplenagem de engenharia; floor plans completos; Design DNA; daylight/vento/ruído avançados; IFC/DWG/BIM completo. Solar ainda não fecha imagery/DSM/roof extraction/shadows 3D calibradas/OCR de conta/tarifas e regulação completas/grid interconnection/estrutura. Esses limites são mantidos explicitamente no código e nos relatórios.

## São Paulo ao vivo

A ferramenta de inspeção agora roda sem exigir banco. A tentativa neste ambiente alcançou a chamada HTTP, mas falhou por **DNS/rede externa indisponível** ao resolver `wfs.geosampa.prefeitura.sp.gov.br`. Portanto nenhum dado ao vivo foi ingerido ou homologado aqui. Permanecem necessários sync real, QA, promoção lote/zona e 10–20 golden lots revisados por profissional.

## Gates externos pendentes

1. `package-lock.json` real, `npm ci`, typecheck e builds;
2. PostgreSQL/PostGIS real com migrations RC3 e testes RLS/cross-tenant;
3. Docker Compose E2E;
4. OpenSearch + embeddings/model/reranker reais e evals;
5. GeoSampa live e golden lots de São Paulo;
6. browser E2E e acessibilidade;
7. staging, carga, pentest, canary, backup/restore e DR.

## Próxima prioridade após RC3

Fechar o runtime real do núcleo e São Paulo ponta a ponta antes de expandir agressivamente: DB/runtime → GeoSampa/golden lots → retrieval/provider reais → browser E2E. Em paralelo, a próxima profundidade funcional do A.I TEC é garagem avançada/TIN/Building+Unit Solver; do Solar é imagery/DSM/shadow/tariff/OCR/calibration.
