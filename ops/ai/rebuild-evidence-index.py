#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

import psycopg
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'workers' / 'ai-ingest'))
from index_schema import embedding_fingerprint, index_mapping  # noqa: E402


def required(name: str) -> str:
    value = str(os.getenv(name, '')).strip()
    if not value:
        raise SystemExit(f'{name} is required')
    return value


def os_auth():
    user = str(os.getenv('OPENSEARCH_USERNAME', '')).strip()
    password = str(os.getenv('OPENSEARCH_PASSWORD', '')).strip()
    return (user, password) if (user or password) else None


def safe_index_name(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{1,254}', value):
        raise SystemExit('OPENSEARCH_EVIDENCE_INDEX must be a concrete lowercase index name')
    if value in {'.', '..'}:
        raise SystemExit('invalid index name')
    return value


def index_descriptor(base: str, index: str):
    response = requests.get(f'{base}/{index}/_mapping', auth=os_auth(), timeout=15)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    raw = response.json()
    return raw.get(index) or next(iter(raw.values()), None)


def db_counts(database_url: str):
    with psycopg.connect(database_url) as connection:
        total, pending = connection.execute(
            """select count(*), count(*) filter (where indexed_at is null)
               from ingest.document_text"""
        ).fetchone()
        return int(total), int(pending)


def requeue_all(database_url: str) -> int:
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            cursor = connection.execute(
                "update ingest.document_text set indexed_at=null,index_error=null"
            )
            return int(cursor.rowcount or 0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Recreate the configured evidence index and requeue canonical DB rows for ai-ingest.'
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Perform destructive index recreation and DB requeue. Default is plan-only.',
    )
    parser.add_argument(
        '--confirm-index',
        default='',
        help='Required with --apply; must exactly equal OPENSEARCH_EVIDENCE_INDEX.',
    )
    args = parser.parse_args()

    base = required('OPENSEARCH_URL').rstrip('/')
    database_url = required('PLATFORM_DATABASE_URL')
    index = safe_index_name(required('OPENSEARCH_EVIDENCE_INDEX'))
    model = str(os.getenv('AI_EMBEDDINGS_MODEL', '')).strip()
    revision = str(os.getenv('AI_EMBEDDINGS_REVISION', '')).strip() or model
    dimension = max(1, int(os.getenv('AI_EMBEDDINGS_DIMENSION', '1536')))
    fingerprint = embedding_fingerprint(model, revision, dimension) if model else None

    descriptor = index_descriptor(base, index)
    mappings = (descriptor or {}).get('mappings') or {}
    current_meta = mappings.get('_meta') or {}
    total, pending = db_counts(database_url)
    plan = {
        'mode': 'apply' if args.apply else 'plan',
        'index': index,
        'indexExists': descriptor is not None,
        'schemaVersionCurrent': current_meta.get('schema_version'),
        'embeddingModel': model or None,
        'embeddingRevision': revision or None,
        'embeddingDimension': dimension,
        'embeddingFingerprint': fingerprint,
        'currentEmbeddingFingerprint': current_meta.get('embedding_fingerprint'),
        'canonicalRows': total,
        'currentlyPendingRows': pending,
        'action': 'delete_and_recreate_index_then_requeue_all_canonical_rows',
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))

    if not args.apply:
        return 0
    if args.confirm_index != index:
        raise SystemExit('--apply requires --confirm-index with the exact configured index name')

    if descriptor is not None:
        response = requests.delete(f'{base}/{index}', auth=os_auth(), timeout=30)
        response.raise_for_status()

    response = requests.put(
        f'{base}/{index}',
        json=index_mapping(dimension, model, revision),
        auth=os_auth(),
        timeout=30,
    )
    response.raise_for_status()
    requeued = requeue_all(database_url)

    print(json.dumps({
        'status': 'REBUILD_QUEUED',
        'index': index,
        'requeuedRows': requeued,
        'embeddingFingerprint': fingerprint,
        'nextStep': 'run/restart ai-ingest and wait until indexed_at is populated; then execute retrieval evals',
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
