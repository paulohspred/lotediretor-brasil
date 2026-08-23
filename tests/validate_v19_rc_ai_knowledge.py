from pathlib import Path

sql=Path('db/platform/migrations/193_v19_rc_ai_knowledge_plane.sql').read_text()
for needle in (
    'ALTER TABLE ingest.document_text ALTER COLUMN tenant_id DROP NOT NULL',
    'retrieval_allowed boolean NOT NULL DEFAULT false',
    "visibility='PUBLIC'",
    'document_version_id uuid REFERENCES legal.document_version',
    'trg_ai_reindex_legal_version',
    'FORCE ROW LEVEL SECURITY',
): assert needle in sql,needle

legal=Path('workers/data-pipelines/legal_ingest.py').read_text()
for needle in (
    "tenant_id,domain,document_id,chunk_index,text_content",
    "'PUBLIC'",
    "status in {'REVIEWED','PUBLISHED','ACTIVE','CONFIRMED'}",
    "document_version_id",
    "No legal.rule is confirmed automatically.",
): assert needle in legal,needle

docs=Path('workers/documents/main.py').read_text();chunking=Path('workers/documents/chunking.py').read_text()
for needle in ('semantic_chunks',"'page_number'","retrieval_allowed","source_locator"):
    assert needle in docs,needle
for needle in ('PAGE_RE','<<<PAGE:',"'page_number'","'locator'"):
    assert needle in chunking,needle

retrieval=Path('services/ai-gateway/src/retrieval.ts').read_text()
assert "retrieval_allowed:true" in retrieval
assert "visibility:'PUBLIC'" in retrieval
assert "municipalityIbge_or_documentIds_required_for_public_retrieval" in retrieval
assert "valid_from" in retrieval and "valid_to" in retrieval
assert 'exactLegalBoost' in retrieval

worker=Path('workers/ai-ingest/main.py').read_text()
for needle in ('lotediretor-evidence-v3',"'visibility':{'type':'keyword'}","'retrieval_allowed':{'type':'boolean'}",'embedding_model'):
    assert needle in worker,needle

print('v19-rc AI knowledge plane public/private + temporal safety OK')
