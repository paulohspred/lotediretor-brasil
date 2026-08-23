# AI ingest / Hybrid RAG index — v19 alpha

Indexa `ingest.document_text` no OpenSearch preservando isolamento por `tenant_id`, domínio, documento e escopo (condomínio ou workspace municipal).

## Busca

- lexical BM25 em português sempre disponível quando OpenSearch está configurado;
- vetor HNSW/KNN quando um endpoint de embeddings compatível é configurado;
- o `ai-gateway` executa lexical + vetor separadamente e faz Reciprocal Rank Fusion (RRF);
- filtros de tenant e escopo são aplicados dentro da query antes de o conteúdo ser devolvido ao modelo.

## Variáveis

- `OPENSEARCH_URL`
- `OPENSEARCH_EVIDENCE_INDEX` (default `lotediretor-evidence-v3`)
- `OPENSEARCH_USERNAME` / `OPENSEARCH_PASSWORD` opcionais
- `AI_EMBEDDINGS_ENDPOINT`
- `AI_EMBEDDINGS_MODEL`
- `AI_EMBEDDINGS_API_KEY` (fallback `AI_API_KEY`)
- `AI_EMBEDDINGS_DIMENSION` (default `1536`)

Se embeddings não estiverem configurados, a indexação e o chat continuam em modo lexical/degradado. A troca de dimensão exige novo índice; não altere a dimensão de um índice já criado.
