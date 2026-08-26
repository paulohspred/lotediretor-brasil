from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'workers' / 'ai-ingest'))

from index_schema import SCHEMA_VERSION, embedding_fingerprint, index_mapping  # noqa: E402

fp = embedding_fingerprint('embedding-model-v1', 'revision-2026-08-25', 1536)
assert len(fp) == 64
assert fp == embedding_fingerprint('embedding-model-v1', 'revision-2026-08-25', 1536)
assert fp != embedding_fingerprint('embedding-model-v1', 'revision-2026-08-26', 1536)
assert fp != embedding_fingerprint('embedding-model-v2', 'revision-2026-08-25', 1536)
assert fp != embedding_fingerprint('embedding-model-v1', 'revision-2026-08-25', 3072)

mapping = index_mapping(1536, 'embedding-model-v1', 'revision-2026-08-25')
meta = mapping['mappings']['_meta']
props = mapping['mappings']['properties']
assert meta['schema_version'] == SCHEMA_VERSION == 'evidence-v20.1'
assert meta['embedding_model'] == 'embedding-model-v1'
assert meta['embedding_revision'] == 'revision-2026-08-25'
assert meta['embedding_dimension'] == 1536
assert meta['embedding_fingerprint'] == fp
assert props['embedding']['type'] == 'knn_vector'
assert props['embedding']['dimension'] == 1536
assert props['embedding_fingerprint']['type'] == 'keyword'
assert props['embedding_revision']['type'] == 'keyword'
assert props['embedding_dimension']['type'] == 'integer'

serialized = repr(mapping).lower()
for forbidden in ['api_key', 'authorization', 'password', 'secret', 'endpoint']:
    assert forbidden not in serialized

rebuild = (root / 'ops/ai/rebuild-evidence-index.py').read_text()
for required in [
    '--apply', '--confirm-index', 'delete_and_recreate_index_then_requeue_all_canonical_rows',
    'update ingest.document_text set indexed_at=null,index_error=null', 'index_mapping',
]:
    assert required in rebuild, required
assert 'requests.delete' in rebuild
assert "if not args.apply" in rebuild
assert "args.confirm_index != index" in rebuild

worker = (root / 'workers/ai-ingest/main.py').read_text()
for required in [
    'opensearch_embedding_dimension_mismatch', 'opensearch_embedding_fingerprint_mismatch',
    'embedding_revision', 'embedding_fingerprint', 'embedding_dimension', 'rebuild_required',
    'refresh=wait_for',
]:
    assert required in worker, required

# indexed_at is consumed by runtime callers as a search-readiness signal. The
# OpenSearch write therefore has to wait for refresh before the DB flag is set.
refresh_write = worker.index('refresh=wait_for')
indexed_ready = worker.index('update ingest.document_text set indexed_at=now()')
assert refresh_write < indexed_ready

print('v20 AI evidence index schema/version/rebuild/search-readiness contracts OK')
