# V19 Alpha — relatório de implementação e próximos gates

## Objetivo

Esta versão não tenta aumentar artificialmente o percentual de conclusão. Ela fecha problemas encontrados na auditoria da v18 e cria infraestrutura necessária para cumprir a Seção 32 do Blueprint sem mascarar ausência de dados reais, validação humana ou runtime.

## Reparos herdados da v18

- dependências internas dos apps alinhadas à versão corrente;
- CI/release gate apontando para o validator corrente;
- variáveis de banco de workers/event dispatcher presentes no compose validation;
- strings de runtime antigas removidas;
- manifest SHA-256 corrigido;
- UI corrente atualizada para v19-alpha;
- lockfile permanece pendente por indisponibilidade do registry neste ambiente.

## AI Core

- `services/ai-gateway/src/retrieval.ts`: BM25 + vector kNN opcional + RRF;
- filtro obrigatório de `tenant_id` e filtros de domínio/scope/município/documento;
- `workers/ai-ingest` usa índice `lotediretor-evidence-v2`, mapping estrito e `knn_vector`;
- provider de embeddings é configurável e lexical continua funcionando em modo degradado;
- `/ai/v1/retrieve`, health de retrieval/embeddings e trace de modo/contagens;
- golden cases não são benchmarks jurídicos: verificam apenas grounded/abstain contracts.

## A.I TEC

- envelope direcional por linhas de borda explícitas; frente/lateral/fundos não são inferidos;
- validator de hard constraints: métrica ausente ou operador desconhecido = `UNVERIFIED`;
- apenas `PASS` recebe `VALIDATED_PRELIMINARY`;
- ranking exclui `PRELIMINARY_UNVERIFIED` e cenários inválidos.

## Município laboratório / dados

- camada de lote oficial PMSP mapeada como `geoportal:lote_cidadao`;
- zoneamento Lei 18.177/2024 mapeado como `geoportal:perimetro_zona_lei_18177_24`;
- WFS passa `srsName=EPSG:4326` explicitamente;
- publicação agora possui `dataset_code`, permitindo múltiplos datasets ativos do mesmo WFS;
- `inspect-wfs` captura chaves/propriedades antes de qualquer mapping de domínio;
- `promote-parcels` e `promote-zones` convertem somente snapshot publicado/QA para tabelas canônicas;
- zonas fragmentadas são dissolvidas por código antes de entrar em `planning.zone`;
- vigência de zoneamento é argumento obrigatório; não é inferida da data de ingestão.

## Legal / territorial

- PDFs recebem marcadores de página durante extração;
- capítulos/seções/artigos viram `legal.article` com locator reproduzível;
- candidatos a parâmetro apontam ao artigo e permanecem `CANDIDATE`;
- TO/TP em `%` são normalizados para razão somente durante cálculo;
- regras confirmadas conflitantes no mesmo escopo/condição bloqueiam o cálculo afetado e colocam a análise em `NEEDS_REVIEW`;
- regra municipal sem `zone_code` pode coexistir com regra específica de zona; a específica tem precedência quando não há conflito interno.

## Próximo gate de verdade

A próxima versão deve ser promovida a beta apenas depois de um município laboratório real passar:

`WFS inspect → sync → QA → domain promotion → lei/documento → revisão de regras → Parcel Resolver → análise → relatório/evidência → 10–20 lotes ouro revisados por profissional.`

Depois disso, a sequência é: fontes nacionais reais, AI eval runtime, Imóvel 360/RE Rural sobre dados reais, Condomínio, Solar avançado, A.I TEC generativo, Prefeitura/Admin e factory nacional.
