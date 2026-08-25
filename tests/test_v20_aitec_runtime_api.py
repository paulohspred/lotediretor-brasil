from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'services' / 'aitec-engine'))

from app.advanced_api import OP_REGISTRY, capabilities, execute_operation, serialize_result

required_operations = {
    'unit.solve', 'unit.compare',
    'terrain.tin', 'terrain.contours', 'terrain.plateaus', 'terrain.cut-fill',
    'building.solve', 'parking.basement', 'unit.room-graph',
    'road.evaluate', 'environment.analyze', 'finance.calculate',
    'export.geojson', 'export.kmz', 'export.dxf', 'export.ifc', 'export.xlsx', 'export.pdf', 'export.gltf', 'export.manifest',
    'ingest.dataset', 'ingest.shapefile', 'ingest.gpkg', 'ingest.dxf', 'ingest.ifc',
    'optimization.pareto', 'optimization.diff',
}
assert required_operations <= set(OP_REGISTRY), sorted(required_operations - set(OP_REGISTRY))

caps = capabilities()
assert len(caps) == len(OP_REGISTRY)
assert all(item['solver_version'] for item in caps)
assert next(item for item in caps if item['operation'] == 'terrain.tin')['required_parameters'] == ['samples']

# Exercise a real advanced solver through the runtime registry.
tin = execute_operation('terrain.tin', kwargs={'samples': [
    {'x': 0, 'y': 0, 'z': 100},
    {'x': 10, 'y': 0, 'z': 101},
    {'x': 0, 'y': 10, 'z': 102},
    {'x': 10, 'y': 10, 'z': 103},
]})
assert tin['status'] == 'CALCULATED', tin
assert tin['solver_version'] == 'aitec-terrain-v20.1'
assert tin['triangle_count'] >= 2

# Prove binary ingest can cross the JSON API without filesystem paths.
feature_collection = {
    'type': 'FeatureCollection',
    'features': [
        {'type': 'Feature', 'properties': {'name': 'parcel'}, 'geometry': {'type': 'Point', 'coordinates': [-46.63, -23.55]}}
    ],
}
payload = json.dumps(feature_collection, separators=(',', ':')).encode()
ingested = execute_operation('ingest.dataset', kwargs={
    'filename': 'parcel.geojson',
    'payload': {'$base64': base64.b64encode(payload).decode('ascii')},
})
assert ingested['status'] == 'PARSED'
assert ingested['format'] == 'GEOJSON'
assert ingested['feature_count'] == 1

# Prove binary exports are deterministic and JSON-safe.
exported = execute_operation('export.geojson', kwargs={'feature_collection': feature_collection})
serialized = serialize_result(exported)
assert serialized['$binary']['encoding'] == 'base64'
assert serialized['$binary']['size'] == len(exported)
assert base64.b64decode(serialized['$binary']['data']) == exported

try:
    execute_operation('not.real')
except ValueError as exc:
    assert 'unknown A.I TEC operation' in str(exc)
else:
    raise AssertionError('unknown operations must be rejected')

entrypoint = (root / 'services' / 'aitec-engine' / 'app' / 'entrypoint.py').read_text()
dockerfile = (root / 'services' / 'aitec-engine' / 'Dockerfile').read_text()
assert 'include_router(advanced_router' in entrypoint
assert 'Depends(internal_token)' in entrypoint
assert 'app.entrypoint:app' in dockerfile

print('v20 A.I TEC runtime API registry + binary bridge OK')
