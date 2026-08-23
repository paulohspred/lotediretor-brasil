# v19-rc.1 — Implementation report

## Objetivo

Fechar lacunas estruturais antes de ampliar a superfície funcional: Knowledge Plane jurídico recuperável com autorização e bitemporalidade; políticas de IA mais estritas; e primeiro Site Solver A.I TEC com geometria persistente, validação e reprodutibilidade.

## 1. AI Knowledge Plane v3

### Fonte relacional
`193_v19_rc_ai_knowledge_plane.sql` transforma `ingest.document_text` em representação derivada auditável do conhecimento recuperável. Cada row pode registrar visibilidade, status, autorização de retrieval, município/scope, página/seção, ACL, versão documental e snapshot.

Há dois eixos temporais:
- **legal time**: `valid_from/valid_to`;
- **system knowledge time**: `recorded_at/superseded_at`.

Isso permite reproduzir tanto “qual regra valia na data X?” quanto “o que o sistema conhecia na data Y?”.

### Publicação segura
- privado: tenant/ACL/scope;
- público: `tenant_id IS NULL`, `visibility=PUBLIC`, mas retrieval exige município ou IDs documentais explícitos;
- DRAFT/EXTRACTED não entra em retrieval;
- mudanças de status/vigência/snapshot/supersessão zeram `indexed_at` para reconstrução.

### Retrieval
O gateway executa:
1. filtros de autorização, jurisdição, status, legal time e knowledge time;
2. lexical BM25;
3. vector search quando embeddings estão configurados;
4. RRF;
5. reranking determinístico com cobertura de termos e boost para tokens jurídicos exatos;
6. evidence allowlist;
7. abstention quando o contexto não sustenta a resposta.

### Prompt/Tool Registry e risco
A RC registra prompts e ferramentas por ID/versão e aplica allowlist por assistente. Tools de escrita exigem ação explícita. O registry **não é ainda um orchestrator genérico**.

Para consultas de alto risco, resposta decisiva sem regra determinística `CONFIRMED` aplicável é convertida em `NÃO DETERMINADO`; quando existe regra confirmada, a revisão profissional é marcada como obrigatória.

### Limite
O caminho foi validado por contratos/código, não com OpenSearch, embeddings e model provider reais nesta execução.

## 2. Ingestão documental/jurídica

- PDF/texto preserva marcadores de página;
- `semantic_chunks()` evita truncamento cego e mantém locator/page;
- upload municipal cria versão legal institucional em estado não homologado;
- ingestão oficial pública reutiliza ato canônico, cria versão por hash e fecha o intervalo temporal anterior quando existe data efetiva nova;
- artigos públicos entram no Knowledge Plane como corpus reconstruível;
- nenhuma ingestão automática cria regra `CONFIRMED`.

## 3. A.I TEC Site Solver MVP

### Engine
`POST /aitec/v1/site-solver`:
- valida GeoJSON;
- projeta para UTM apropriado;
- cria envelope por setback;
- gera alternativas retangulares diversificadas e reproduzíveis por seed;
- impede footprint fora do envelope e overlap entre buildings;
- calcula footprint, gross/net area, unidades e parking land-budget preliminar;
- valida CA/TO/TP/altura desta fase;
- calcula Pareto não dominado.

### Persistência
`194_v19_rc_aitec_site_solver.sql` adiciona:
- `aitec.solution`;
- `aitec.geometry_object`;
- `aitec.violation`;
- `aitec.solution_lock`.

Todos entram no modelo multi-tenant/RLS. `solution_lock` é a base de dados para o futuro lock/branch/regenerate; o workflow completo ainda não está pronto.

### API/UI
- `POST /api/v1/aitec/projects/:id/solutions/generate`
- `GET /api/v1/aitec/projects/:id/solutions`
- `GET /api/v1/aitec/solutions/:solutionId`

A UI permite terreno GeoJSON, setback, parâmetros urbanísticos, metas preliminares, count e seed; lista alternativas, KPIs e Pareto.

### Limites
Ainda faltam no A.I TEC: viário, parking geometry/rampas, terrain/cut-fill, Building Solver, core/circulação, Unit Solver/planta, Design DNA operacional, lock+regenerate, BIM/CAD completo e análises ambientais avançadas.

## 4. Segurança/evidência

- regra documental e `legal.rule` são camadas distintas;
- retrieval não substitui cálculo determinístico;
- documentos recuperados não ganham autoridade para tool calls;
- public retrieval precisa de escopo;
- provider só pode usar evidências permitidas pelo backend;
- conclusões de alto risco têm gate determinístico.

## 5. Critério de promoção

A RC não deve virar produção até existirem evidências de: build reproduzível; PostgreSQL/PostGIS + RLS runtime; Docker E2E; OpenSearch/embeddings/provider reais; São Paulo live/golden lots; browser E2E/acessibilidade; pentest/canary; backup/restore e DR.
