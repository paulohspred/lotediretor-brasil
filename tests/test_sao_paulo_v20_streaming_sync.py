import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'workers' / 'data-pipelines'))

import sao_paulo_streaming_sync as stream


PROFILE = {
    'municipality_ibge': '3550308',
    'name': 'São Paulo',
    'sources': [{
        'code': 'SP_GEOSAMPA_WFS',
        'authority': 'Prefeitura de São Paulo',
        'channel': 'WFS',
        'base_url': 'https://example.test/geoserver/ows',
        'license': 'CC-BY-SA-4.0',
        'license_url': 'https://example.test/license',
        'datasets': [{
            'code': 'PARCEL',
            'typename': 'geoportal:lote_cidadao',
            'requested_crs': 'EPSG:4326',
            'source_revision': 'test',
            'target_layer_code': 'SP_GEOSAMPA_PARCEL',
            'domain': 'CADASTRE',
            'canonical_mapping': {
                'official_identifier_field': 'cd_identificador',
                'land_area_m2_field': 'qt_area_terreno',
            },
        }],
    }],
}


def feature(index: int, marker: str | None = None):
    return {
        'type': 'Feature',
        'id': marker or f'lote_cidadao.{index}',
        'properties': {
            'cd_identificador': f'SQL-{index:06d}',
            'qt_area_terreno': 125.0 + index,
        },
        'geometry': {
            'type': 'Polygon',
            'coordinates': [[[-46.70, -23.60], [-46.69, -23.60], [-46.69, -23.59], [-46.70, -23.60]]],
        },
    }


class FakeResponse:
    status_code = 200

    def __init__(self, payload, url='https://example.test/ows'):
        self._payload = payload
        self.url = url

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, features):
        self.features = features
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        params = dict(params or {})
        self.calls.append(params)
        start = int(params['startIndex'])
        count = int(params['count'])
        rows = self.features[start:start + count]
        return FakeResponse({'type': 'FeatureCollection', 'features': rows}, f'{url}?startIndex={start}&count={count}')


class FakeStore:
    def __init__(self):
        self.objects = {}

    def put_object(self, **kwargs):
        self.objects[kwargs['Key']] = bytes(kwargs['Body'])
        return {'ETag': 'fake'}


class StreamingSyncTests(unittest.TestCase):
    def setUp(self):
        self.previous = os.environ.get('SP_GEOSAMPA_PARCEL_STREAM_PAGE_SIZE')
        os.environ['SP_GEOSAMPA_PARCEL_STREAM_PAGE_SIZE'] = '100'

    def tearDown(self):
        if self.previous is None:
            os.environ.pop('SP_GEOSAMPA_PARCEL_STREAM_PAGE_SIZE', None)
        else:
            os.environ['SP_GEOSAMPA_PARCEL_STREAM_PAGE_SIZE'] = self.previous

    def _hits(self, values):
        queue = list(values)
        def fake_hits(session, base_url, typename):
            value = queue.pop(0)
            return value, {'mode': 'WFS_HITS_ONLY', 'http_status': 200, 'url': base_url}
        return fake_hits

    def test_stages_complete_dataset_pagewise_without_feature_accumulation(self):
        rows = [feature(i) for i in range(205)]
        session = FakeSession(rows)
        store = FakeStore()
        original = stream.fetch_hits
        stream.fetch_hits = self._hits([205, 205])
        try:
            manifest = stream.stage_dataset(PROFILE, 'PARCEL', session=session, object_store=store)
        finally:
            stream.fetch_hits = original
        self.assertEqual(manifest['expected_records'], 205)
        self.assertEqual(manifest['received_records'], 205)
        self.assertEqual([p['records'] for p in manifest['pages']], [100, 100, 5])
        self.assertEqual([c['startIndex'] for c in session.calls], [0, 100, 200])
        self.assertEqual(len(store.objects), 4)  # three immutable pages + one manifest
        self.assertNotIn('features', manifest)
        self.assertTrue(all(manifest['quality'].values()))
        self.assertTrue(manifest['manifest_object_key'].endswith('.json'))

    def test_repeated_identifier_across_pages_aborts_before_manifest(self):
        rows = [feature(i) for i in range(201)]
        rows[100] = feature(100, marker=rows[0]['id'])
        session = FakeSession(rows)
        store = FakeStore()
        original = stream.fetch_hits
        stream.fetch_hits = self._hits([201])
        try:
            with self.assertRaisesRegex(RuntimeError, 'repeated feature identifier'):
                stream.stage_dataset(PROFILE, 'PARCEL', session=session, object_store=store)
        finally:
            stream.fetch_hits = original
        self.assertFalse(any(key.endswith('.json') and '/manifest-' in key for key in store.objects))

    def test_source_count_change_aborts_mixed_snapshot(self):
        rows = [feature(i) for i in range(120)]
        session = FakeSession(rows)
        store = FakeStore()
        original = stream.fetch_hits
        stream.fetch_hits = self._hits([120, 121])
        try:
            with self.assertRaisesRegex(RuntimeError, 'source changed during sync'):
                stream.stage_dataset(PROFILE, 'PARCEL', session=session, object_store=store)
        finally:
            stream.fetch_hits = original
        self.assertFalse(any('/manifest-' in key for key in store.objects))


if __name__ == '__main__':
    unittest.main()
