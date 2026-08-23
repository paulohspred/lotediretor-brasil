from pathlib import Path
import json,re
root=Path(__file__).resolve().parents[1]

migration=(root/'db/platform/migrations/150_v15_territorial_core.sql').read_text()
for token in [
    'CREATE TABLE IF NOT EXISTS core.asset(',
    'CREATE TABLE IF NOT EXISTS source.coverage(',
    'CREATE TABLE IF NOT EXISTS geo.municipality_boundary(',
    'CREATE TABLE IF NOT EXISTS geo.layer(',
    'CREATE TABLE IF NOT EXISTS geo.feature(',
    'CREATE TABLE IF NOT EXISTS geo.address_index(',
    'CREATE TABLE IF NOT EXISTS legal.article(',
    'CREATE TABLE IF NOT EXISTS analysis.spatial_relation(',
    'CREATE TABLE IF NOT EXISTS analysis.calculation(',
    'CREATE TABLE IF NOT EXISTS analysis.snapshot_ref(',
    'CREATE TABLE IF NOT EXISTS municipality.lab_profile('
]:
    assert token in migration,token
assert 'SP_GEOSAMPA_WFS' in migration and 'SP_LEGISLACAO_PDE' in migration
assert "'NOT_INGESTED'" in migration

controller=(root/'services/platform-api/src/territorial/territorial.controller.ts').read_text()
for route in ["@Post('parcel/resolve')","@Get('municipalities/:ibge/coverage')","@Get('legal/search')","@Get('legal/rules/effective')","@Post('spatial/intersections')","@Get('nearby')","@Post('analysis')","@Get('analysis/:id/evidence')"]:
    assert route in controller,route
assert "@Get('parcel/resolve')" in controller
assert 'withIdempotency' in controller and 'analysis.v' in controller
assert 'enqueueOutbox' in controller and "'analysis.completed'" in controller
core=(root/'services/platform-api/src/core.module.ts').read_text()
assert "@Get('parcel/resolve')" not in core
assert "@Post('analysis')" not in core

service=(root/'services/platform-api/src/territorial/territorial.service.ts').read_text()
for capability in ['POINT_COVERED','POLYGON_OVERLAP','ADDRESS_INDEX','ASSET_IDENTIFIER','POTENTIAL_MAX_M2','MAX_PROJECTION_M2','MIN_PERMEABLE_M2','analysis.snapshot_ref']:
    assert capability in service,capability
assert "status='CONFIRMED'" in service

profile=json.loads((root/'data/municipality-labs/sao-paulo-3550308.json').read_text())
assert profile['municipality_ibge']=='3550308'
assert profile['status'] in {
    'DISCOVERED',
    'CORE_LAYERS_MAPPED_PENDING_RUNTIME_SYNC',
    'CORE_LAYERS_LIVE_SCHEMA_VERIFIED_PENDING_RUNTIME_SYNC',
}
assert any(s['code']=='SP_GEOSAMPA_WFS' for s in profile['sources'])
assert any(s['code']=='SP_LEGISLACAO_PDE' for s in profile['sources'])
# Later versions may safely promote exact WFS mappings and live schema evidence after review.
for source in profile['sources']:
    for ds in source.get('datasets',[]):
        if source['channel']=='WFS':
            assert ds.get('status') in {
                'MAPPING_REQUIRED',
                'MAPPED_PENDING_INGESTION',
                'LIVE_SCHEMA_VERIFIED_PENDING_INGESTION',
                'CATALOG_MAPPING_REQUIRED',
            }

route_catalog=(root/'services/platform-api/src/contracts/route-catalog.ts').read_text()
for path in ['/api/v1/parcel/resolve','/api/v1/legal/search','/api/v1/spatial/intersections','/api/v1/analysis/{id}/evidence']:
    assert path in route_catalog,path

print('v15 territorial contracts OK')
