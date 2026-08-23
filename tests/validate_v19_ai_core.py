from pathlib import Path


def must(path: str, *needles: str):
    text = Path(path).read_text()
    for needle in needles:
        assert needle in text, f"{path}: missing {needle}"
    return text

retrieval = must(
    'services/ai-gateway/src/retrieval.ts',
    "term:{retrieval_allowed:true}",
    "term:{tenant_id:tenantId}",
    "term:{visibility:'PUBLIC'}",
    "scope_id:String(scope.scopeId)",
    "municipality_ibge:String(scope.municipalityIbge)",
    "multi_match",
    "knn:{embedding",
    "function rrf",
    "function exactLegalBoost",
    "mode:vectorHits.length?'hybrid_rrf_legal_rerank':'lexical_legal_rerank'",
)
assert retrieval.index("term:{retrieval_allowed:true}") < retrieval.index('multi_match'), 'authorization/status filter must be built before lexical query'
assert "municipalityIbge_or_documentIds_required_for_public_retrieval" in retrieval

embeddings = must(
    'services/ai-gateway/src/embeddings.ts',
    'AI_EMBEDDINGS_ENDPOINT',
    'AI_EMBEDDINGS_MODEL',
    'AI_EMBEDDINGS_DIMENSION',
    'embeddings_invalid_vector',
)

gateway = must(
    'services/ai-gateway/src/main.ts',
    "app.post('/ai/v1/retrieve'",
    'retrieveEvidence',
    'retrievalConfigured',
    'embeddingsConfigured',
    'provider_grounding_gate_failed',
    "status:'ABSTAINED'",
    'decision_status',
    'professional_review',
    'version:VERSION',
)
assert 'lotediretor-evidence-v3' in retrieval

ingest = must(
    'workers/ai-ingest/main.py',
    "'dynamic':'strict'",
    "'type':'knn_vector'",
    "'tenant_id':{'type':'keyword'}",
    "'visibility':{'type':'keyword'}",
    "'knowledge_status':{'type':'keyword'}",
    "'retrieval_allowed':{'type':'boolean'}",
    "'municipality_ibge':{'type':'keyword'}",
    "'valid_from':{'type':'date'}",
    "'valid_to':{'type':'date'}",
    "INDEX=os.getenv('OPENSEARCH_EVIDENCE_INDEX','lotediretor-evidence-v3')",
    'ensure_index()',
)

core = must(
    'services/platform-api/src/core.module.ts',
    "retrieval={enabled:true,domains:['municipality']",
    "retrieval={enabled:true,domains:['condo']",
)

compose = must(
    'docker-compose.yml',
    'OPENSEARCH_EVIDENCE_INDEX',
    'lotediretor-evidence-v3',
    'AI_EMBEDDINGS_ENDPOINT',
    'AI_EMBEDDINGS_MODEL',
    'AI_EMBEDDINGS_DIMENSION',
)

env = must(
    '.env.example',
    'OPENSEARCH_EVIDENCE_INDEX=',
    'AI_EMBEDDINGS_ENDPOINT=',
    'AI_EMBEDDINGS_MODEL=',
    'AI_EMBEDDINGS_DIMENSION=',
)

print('v19 AI Core hybrid/public-private retrieval contracts OK')
