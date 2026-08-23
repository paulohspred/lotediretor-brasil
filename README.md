# LoteDiretor SaaS v19-rc.3

Checkpoint cumulativo do **LoteDiretor Brasil**, implementado contra o Blueprint Final v2.0. A RC3 aprofunda o núcleo que precisa ser confiável antes de ampliar módulos: Core Territorial/Legal, AI Knowledge Plane, laboratório municipal de São Paulo, A.I TEC geometry-aware e Energia Solar com dimensionamento elétrico preliminar baseado em dados explícitos.

## Implementado nesta RC

### A.I TEC — Site/Access/Parking/Program/Terrain/Building
- Site Solver determinístico e reproduzível por `seed`;
- envelope métrico e hard constraints de CA, TO, TP e altura;
- estacionamento de superfície com `PARKING_STALL` e `DRIVE_AISLE`;
- acesso fornecido explicitamente pelo usuário e viário interno conceitual, sem inventar frente de rua;
- `lock + branch + regenerate` preservando footprints travados;
- unit mix determinístico com mínimos tratados como program gate;
- estimativa conceitual de cut/fill somente quando existem amostras XYZ explícitas;
- Building Solver preliminar com floor plate, core e circulação;
- persistência de soluções, geometrias, violações, locks, análises e artefatos;
- exportação de solução em GeoJSON e métricas em CSV;
- Pareto apenas entre alternativas que passaram as restrições duras computáveis.

### Energia Solar — elétrica preliminar
- dimensionamento de strings/MPPT a partir de datasheet explícito;
- correção de Voc/Vmp por temperatura;
- verificação de janela MPPT, tensão DC máxima, corrente por MPPT e limite DC do inversor;
- ausência de especificação retorna `REQUIRES_INPUT` em vez de completar valores por suposição;
- resultados persistidos como `solar.electrical_design` com provenance/review fields;
- correção da unicidade global/tenant de `solar.regulation_snapshot` quando `tenant_id` é `NULL`.

### AI Core / Knowledge Plane
- corpus público, institucional e privado com autorização pré-retrieval;
- bitemporalidade jurídica e de conhecimento;
- lexical + vector opcional + RRF + reranking;
- Prompt/Tool Registry versionado;
- evidence allowlist, abstenção e gate de alto risco baseado em regra `CONFIRMED`;
- page-aware semantic chunks e invalidação/reindexação por mudança de fonte.

### São Paulo / dados municipais
- profile oficial para lote fiscal e zoneamento GeoSampa;
- WFS com CRS solicitado explicitamente;
- publicação por dataset e promoção controlada para `geo.parcel` e `planning.zone`;
- ferramenta `inspect-wfs` não depende mais de PostgreSQL/psycopg para inspeção de fonte;
- comandos que realmente escrevem no banco exigem explicitamente `PLATFORM_DATABASE_URL` e driver;
- falhas de inspeção são emitidas em JSON legível, sem traceback operacional desnecessário.

## Validação local

```bash
./validate-v19-rc3.sh
```

O gate cobre regressões v15–v19, Core/Legal, AI, São Paulo, A.I TEC RC/RC2/RC3, Solar RC3, Python, JSON/YAML, TypeScript/TSX sintático, shell, drift de versão e contratos de migrations. Consulte `VALIDATION.md` para o que foi e o que não foi executado.

## Estado de produção

**Não homologado para produção.** Este checkpoint não fabrica evidência para gates que dependem de infraestrutura indisponível neste ambiente. Continuam obrigatórios: lockfile real + `npm ci/typecheck/build`, PostgreSQL/PostGIS real, Docker E2E, OpenSearch/embeddings/provider reais, GeoSampa ao vivo + golden lots humanos, browser E2E/a11y, pentest, staging/carga/canary e backup/restore/DR.

Consulte `STATUS.md`, `VALIDATION.md`, `REPAIR_NOTES.md`, `PROGRESS.json` e `docs/architecture/V19_RC3_IMPLEMENTATION_REPORT.md`.
