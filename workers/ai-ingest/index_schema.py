from __future__ import annotations

import hashlib

SCHEMA_VERSION = 'evidence-v20.1'


def embedding_fingerprint(model: str, revision: str, dimension: int) -> str:
    """Stable identity for a vector space. It contains no credential or endpoint."""
    normalized_model = str(model or '').strip()
    normalized_revision = str(revision or '').strip() or 'unversioned'
    normalized_dimension = int(dimension)
    if normalized_dimension <= 0:
        raise ValueError('embedding_dimension_must_be_positive')
    payload = f'{normalized_model}|{normalized_revision}|{normalized_dimension}'.encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def index_properties(dimension: int) -> dict:
    dimension = int(dimension)
    if dimension <= 0:
        raise ValueError('embedding_dimension_must_be_positive')
    return {
        'tenant_id': {'type': 'keyword'},
        'domain': {'type': 'keyword'},
        'document_id': {'type': 'keyword'},
        'document_version_id': {'type': 'keyword'},
        'source_snapshot_id': {'type': 'keyword'},
        'chunk_index': {'type': 'integer'},
        'scope_id': {'type': 'keyword'},
        'municipality_ibge': {'type': 'keyword'},
        'visibility': {'type': 'keyword'},
        'knowledge_status': {'type': 'keyword'},
        'retrieval_allowed': {'type': 'boolean'},
        'title': {
            'type': 'text',
            'analyzer': 'portuguese',
            'fields': {'keyword': {'type': 'keyword', 'ignore_above': 512}},
        },
        'locator': {'type': 'keyword', 'ignore_above': 1024},
        'page_number': {'type': 'integer'},
        'section_id': {'type': 'keyword', 'ignore_above': 1024},
        'text': {'type': 'text', 'analyzer': 'portuguese'},
        'valid_from': {'type': 'date'},
        'valid_to': {'type': 'date'},
        'recorded_at': {'type': 'date'},
        'superseded_at': {'type': 'date'},
        'metadata': {'type': 'object', 'enabled': False},
        'acl': {'type': 'object', 'enabled': False},
        'embedding_model': {'type': 'keyword'},
        'embedding_revision': {'type': 'keyword'},
        'embedding_fingerprint': {'type': 'keyword'},
        'embedding_dimension': {'type': 'integer'},
        'embedding': {
            'type': 'knn_vector',
            'dimension': dimension,
            'method': {
                'name': 'hnsw',
                'space_type': 'cosinesimil',
                'engine': 'lucene',
                'parameters': {'ef_construction': 128, 'm': 16},
            },
        },
    }


def index_meta(model: str, revision: str, dimension: int) -> dict:
    normalized_model = str(model or '').strip()
    normalized_revision = str(revision or '').strip()
    return {
        'schema_version': SCHEMA_VERSION,
        'embedding_model': normalized_model or None,
        'embedding_revision': normalized_revision or None,
        'embedding_dimension': int(dimension),
        'embedding_fingerprint': embedding_fingerprint(normalized_model, normalized_revision, dimension)
        if normalized_model
        else None,
    }


def index_mapping(dimension: int, model: str = '', revision: str = '') -> dict:
    return {
        'settings': {'index': {'knn': True}},
        'mappings': {
            'dynamic': 'strict',
            '_meta': index_meta(model, revision, dimension),
            'properties': index_properties(dimension),
        },
    }
