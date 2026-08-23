from pathlib import Path
r=Path('services/ai-gateway/src/retrieval.ts').read_text()
m=Path('services/ai-gateway/src/main.ts').read_text()
i=Path('workers/ai-ingest/main.py').read_text()
for token in ['baseDate?:string','valid_from','valid_to','hybrid_rrf_legal_rerank','termCoverage','rerankScore']:
    assert token in r, token
for token in ['provider_invalid_evidence_id','conditionEvaluation','baseDate:body.retrieval.baseDate||body.baseDate']:
    assert token in m, token
assert "'document_version_id':{'type':'keyword'}" in i and "'valid_from':{'type':'date'}" in i and "'valid_to':{'type':'date'}" in i
print('v19-beta temporal AI grounding contracts OK')
