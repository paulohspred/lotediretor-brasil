from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PIPELINES_DIR = ROOT / 'workers/data-pipelines'
MODULE_PATH = PIPELINES_DIR / 'sao_paulo_ingestion_preflight.py'
sys.path.insert(0, str(PIPELINES_DIR))
spec = importlib.util.spec_from_file_location('sp_preflight', MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class FakeResponse:
    def __init__(self, *, json_payload=None, xml_text=None, url='https://example.test/wfs'):
        self._json = json_payload
        self.status_code = 200
        self.url = url
        if xml_text is not None:
            self.content = xml_text.encode('utf-8')
            self.text = xml_text
            self.headers = {'content-type': 'application/xml'}
        else:
            import json
            self.content = json.dumps(json_payload).encode('utf-8')
            self.text = self.content.decode('utf-8')
            self.headers = {'content-type': 'application/json'}

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, count, properties):
        self.count = count
        self.properties = properties

    def get(self, url, params=None, headers=None, timeout=None):
        if params.get('resultType') == 'hits':
            return FakeResponse(xml_text=f'<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" numberMatched="{self.count}" numberReturned="0"/>')
        return FakeResponse(json_payload={
            'type': 'FeatureCollection',
            'features': [{
                'id': 'sample.1',
                'type': 'Feature',
                'geometry': {'type': 'Polygon', 'coordinates': []},
                'properties': {key: 'x' for key in self.properties},
            }],
        })


def dataset():
    return {
        'code': 'PARCEL',
        'typename': 'geoportal:lote_cidadao',
        'requested_crs': 'EPSG:4326',
        'canonical_mapping': {
            'official_identifier_field': 'cd_identificador',
            'land_area_m2_field': 'qt_area_terreno',
            'not_a_field_constant': 'ignored',
        },
    }


def source():
    return {'base_url': 'https://example.test/wfs'}


def test_ready_when_schema_and_capacity_fit():
    with patch.dict(os.environ, {
        'SP_GEOSAMPA_PARCEL_SOURCE_PAGE_SIZE': '2000',
        'SP_GEOSAMPA_PARCEL_SOURCE_MAX_PAGES': '500',
    }, clear=False):
        out = mod.evaluate_dataset(dataset(), source(), FakeSession(800_000, ['cd_identificador', 'qt_area_terreno']))
    assert out['status'] == 'READY_FOR_FULL_SYNC'
    assert out['estimated_pages'] == 400
    assert out['capacity_ok'] is True
    assert out['schema_ok'] is True


def test_capacity_plan_is_explicit_not_partial_publication():
    with patch.dict(os.environ, {
        'SP_GEOSAMPA_PARCEL_SOURCE_PAGE_SIZE': '2000',
        'SP_GEOSAMPA_PARCEL_SOURCE_MAX_PAGES': '500',
    }, clear=False):
        out = mod.evaluate_dataset(dataset(), source(), FakeSession(1_200_001, ['cd_identificador', 'qt_area_terreno']))
    assert out['status'] == 'FULL_SYNC_REQUIRES_CAPACITY_PLAN'
    assert out['estimated_pages'] == 601
    assert out['capacity_ok'] is False


def test_schema_drift_blocks_sync_even_when_capacity_fits():
    out = mod.evaluate_dataset(dataset(), source(), FakeSession(10, ['cd_identificador']))
    assert out['status'] == 'BLOCKED_SCHEMA_DRIFT'
    assert out['missing_canonical_fields'] == ['qt_area_terreno']
    assert out['schema_ok'] is False


def test_parse_hits_json_and_unknown_rejection():
    assert mod.parse_number_matched(FakeResponse(json_payload={'numberMatched': 42})) == 42
    try:
        mod.parse_number_matched(FakeResponse(json_payload={'numberMatched': 'unknown'}))
    except RuntimeError as exc:
        assert 'finite numberMatched' in str(exc)
    else:
        raise AssertionError('unknown numberMatched must fail')


if __name__ == '__main__':
    test_ready_when_schema_and_capacity_fit()
    test_capacity_plan_is_explicit_not_partial_publication()
    test_schema_drift_blocks_sync_even_when_capacity_fits()
    test_parse_hits_json_and_unknown_rejection()
    print('São Paulo ingestion preflight tests OK')
