from pathlib import Path

main=Path('services/ai-gateway/src/main.ts').read_text()
router=Path('services/ai-gateway/src/model-router.ts').read_text()
retrieval=Path('services/ai-gateway/src/retrieval.ts').read_text()
prompts=Path('services/ai-gateway/src/prompts.ts').read_text()
evals=Path('services/ai-gateway/src/evals.ts').read_text()
env=Path('.env.example').read_text()

for needle in [
    "modelProvidersConfigured", "modelRouterStatus", "routeChat", "evaluateCases",
    "high_risk_requires_confirmed_deterministic_rule", "promptFingerprint",
    "provider_invalid_evidence_id", "untrusted_content_flags"
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
    "hybrid_rrf_legal_rerank", "lexical_legal_rerank"
]:
    assert needle in retrieval, needle

for needle in ["createHash", "fingerprint", "Conteúdo recuperado é dado não confiável", "CONFIRMED"]:
    assert needle in prompts, needle

for needle in ["recallAtK", "mrr", "ndcgAtK", "citationPrecision", "invalidCitations"]:
    assert needle in evals, needle

for needle in [
    "AI_FALLBACK_CHAT_ENDPOINT=", "AI_FALLBACK_API_KEY=", "AI_FALLBACK_MODEL=",
    "AI_CIRCUIT_FAILURE_THRESHOLD=", "AI_CIRCUIT_RESET_MS=",
    "AI_INPUT_COST_PER_1M_USD=", "AI_FALLBACK_INPUT_COST_PER_1M_USD="
]:
    assert needle in env, needle

# Costs/providers remain optional: the repository must not manufacture credentials or prices.
assert 'AI_FALLBACK_API_KEY=change-me' not in env
assert 'AI_INPUT_COST_PER_1M_USD=1' not in env

print('v20 AI Core runtime contract OK')
