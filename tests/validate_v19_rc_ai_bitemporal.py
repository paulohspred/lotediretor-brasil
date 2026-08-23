from pathlib import Path

migration = Path('db/platform/migrations/193_v19_rc_ai_knowledge_plane.sql').read_text()
for token in (
    'recorded_at timestamptz',
    'superseded_at timestamptz',
    'recorded_at=dv.recorded_at',
    'superseded_at=dv.superseded_at',
    'superseded_at=NEW.superseded_at',
    'AFTER UPDATE OF status,valid_from,valid_to,source_snapshot_id,superseded_at',
):
    assert token in migration, token

legal = Path('workers/data-pipelines/legal_ingest.py').read_text()
assert 'superseded_at=now()' in legal
assert 'valid_to=%s::timestamptz' in legal
assert "valid_from < %s::timestamptz" in legal
assert 'recorded_at,superseded_at,document_version_id' in legal

indexer = Path('workers/ai-ingest/main.py').read_text()
assert "'recorded_at':{'type':'date'}" in indexer
assert "'superseded_at':{'type':'date'}" in indexer
assert 'recorded_at,superseded_at,document_version_id' in indexer

retrieval = Path('services/ai-gateway/src/retrieval.ts').read_text()
for token in (
    'knowledgeAt?:string',
    "recorded_at:{lte:knowledgeAt}",
    "superseded_at:{gt:knowledgeAt}",
    "knowledgeAt_must_be_ISO8601",
    "recordedAt:h._source?.recorded_at||null",
    "supersededAt:h._source?.superseded_at||null",
):
    assert token in retrieval, token

main = Path('services/ai-gateway/src/main.ts').read_text()
assert 'knowledgeAt:body.retrieval.knowledgeAt' in main

print('v19-rc bitemporal AI retrieval contracts OK')
