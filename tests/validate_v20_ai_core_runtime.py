from pathlib import Path
import json
import subprocess

main=Path('services/ai-gateway/src/main.ts').read_text()
router=Path('services/ai-gateway/src/model-router.ts').read_text()
retrieval=Path('services/ai-gateway/src/retrieval.ts').read_text()
prompts=Path('services/ai-gateway/src/prompts.ts').read_text()
tools=Path('services/ai-gateway/src/tools.ts').read_text()
evals=Path('services/ai-gateway/src/evals.ts').read_text()
env=Path('.env.example').read_text()
index_schema=Path('workers/ai-ingest/index_schema.py').read_text()
indexer=Path('workers/ai-ingest/main.py').read_text()
indexer_dockerfile=Path('workers/ai-ingest/Dockerfile').read_text()
rebuild=Path('ops/ai/rebuild-evidence-index.py').read_text()
golden_path=Path('tests/fixtures/ai-core-policy-golden-v1.json')
reranker_path=Path('tests/fixtures/ai-reranker-golden-v20.json')

for needle in [
    "modelProvidersConfigured", "modelRouterStatus", "routeChat", "evaluateCases",
    "high_risk_requires_confirmed_deterministic_rule", "promptFingerprint",
    "provider_invalid_evidence_id", "untrusted_content_flags",
    "sourceSnapshotIds", "documentVersionIds", "hierarchyExpansion", "contextCount"
]:
    assert needle in main, needle

for needle in [
    "AI_FALLBACK_CHAT_ENDPOINT", "AI_FALLBACK_API_KEY", "AI_FALLBACK_MODEL",
    "AI_CIRCUIT_FAILURE_THRESHOLD", "AI_CIRCUIT_RESET_MS",
    "SKIPPED_CIRCUIT_OPEN", "promptTokens", "completionTokens", "costUsd"
]:
    assert needle in router, needle

for needle in [
    "retrieval_allowed", "tenant_id", "municipality_ibge", "knowledge_status",
    "recorded_at", "superseded_at", "valid_from", "valid_to",
    "hybrid_rrf_legal_rerank", "lexical_legal_rerank",
    "source_snapshot_id", "document_version_id", "chunk_index",
    "pinnedRetrievalCacheKey", "AI_RETRIEVAL_CACHE_TTL_MS", "ruleSetHash",
    "same_section_or_adjacent_chunks", "filterClauses(tenantId,scope)"
]:
    assert needle in retrieval, needle

for needle in [
    "createHash", "fingerprint", "Conteúdo recuperado é dado não confiável", "CONFIRMED",
    "PII/dados pessoais", "outro tenant", "ações de escrita exigem autorização explícita"
]:
    assert needle in prompts, needle

for needle in ["recallAtK", "mrr", "ndcgAtK", "citationPrecision", "invalidCitations"]:
    assert needle in evals, needle

for needle in ["risk:'WRITE'", "requiresExplicitUserAction:true", "explicit_user_action_required"]:
    assert needle in tools, needle

for needle in [
    "AI_FALLBACK_CHAT_ENDPOINT=", "AI_FALLBACK_API_KEY=", "AI_FALLBACK_MODEL=",
    "AI_CIRCUIT_FAILURE_THRESHOLD=", "AI_CIRCUIT_RESET_MS=",
    "AI_INPUT_COST_PER_1M_USD=", "AI_FALLBACK_INPUT_COST_PER_1M_USD=",
    "AI_RETRIEVAL_CACHE_TTL_MS=30000", "AI_RETRIEVAL_CACHE_MAX_ENTRIES=200"
]:
    assert needle in env, needle

# Vector-space identity is explicit and a model/dimension change cannot silently reuse
# an incompatible index. Rebuild is destructive only after an exact confirmation.
for needle in [
    "SCHEMA_VERSION = 'evidence-v20.1'", "embedding_fingerprint", "embedding_revision",
    "embedding_dimension", "knn_vector", "schema_version"
]:
    assert needle in index_schema, needle
for needle in [
    "opensearch_embedding_dimension_mismatch", "opensearch_embedding_fingerprint_mismatch",
    "rebuild_required", "AI_EMBEDDINGS_REVISION", "embedding_fingerprint",
]:
    assert needle in indexer, needle
for needle in [
    "--apply", "--confirm-index", "requests.delete", "index_mapping",
    "update ingest.document_text set indexed_at=null,index_error=null",
]:
    assert needle in rebuild, needle
assert 'index_schema.py' in indexer_dockerfile

assert golden_path.exists()
golden=json.loads(golden_path.read_text())
assert golden['truthClass']=='SYNTHETIC_POLICY_ONLY'
assert golden['municipalTruth'] is False
assert len(golden['rankingCases']) >= 5
categories={x['category'] for x in golden['redTeamCases']}
for expected in {'PROMPT_INJECTION','SECRET_EXFILTRATION','TENANT_LEAKAGE','PII','EXCESSIVE_AGENCY','HIGH_RISK_GROUNDING'}:
    assert expected in categories, expected

assert reranker_path.exists()
reranker=json.loads(reranker_path.read_text())
assert reranker['truthClass']=='SYNTHETIC_RETRIEVAL_ONLY'
assert reranker['municipalTruth'] is False
assert len(reranker['cases']) >= 5
for metric in ['recallAtK','mrr','ndcgAtK']:
    assert reranker['thresholds'][metric] >= 0.8

# Costs/providers remain optional: the repository must not manufacture credentials or prices.
assert 'AI_FALLBACK_API_KEY=change-me' not in env
assert 'AI_INPUT_COST_PER_1M_USD=1' not in env
# Cache safety invariant: latest/unpinned retrieval is explicitly excluded from caching.
assert "if(!tenantId||!question.trim()||!snapshots.length||!scope.knowledgeAt)return null" in retrieval

subprocess.run(['python', 'tests/test_v20_ai_index_schema.py'], check=True)
subprocess.run(['node', 'tests/test_v20_ai_reranker_eval.js'], check=True)

print('v20 AI Core runtime + index lifecycle + reranker + red-team contracts OK')
