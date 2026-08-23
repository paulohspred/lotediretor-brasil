import json
from pathlib import Path

R=Path(__file__).resolve().parents[1]
d=json.loads((R/'data/municipality-labs/sao-paulo-3550308.json').read_text())
assert d['municipality_ibge']=='3550308'
assert d['status']=='CORE_LAYERS_LIVE_SCHEMA_VERIFIED_PENDING_RUNTIME_SYNC'
wfs=next(x for x in d['sources'] if x['code']=='SP_GEOSAMPA_WFS')
by={x['code']:x for x in wfs['datasets']}
parcel=by['PARCEL']; zoning=by['ZONEAMENTO']
assert parcel['typename']=='geoportal:lote_cidadao'
assert zoning['typename']=='geoportal:perimetro_zona_lei_18177_24'
for x in (parcel,zoning):
    assert x['status']=='LIVE_SCHEMA_VERIFIED_PENDING_INGESTION'
    assert x['metadata_url'].startswith('https://metadados.geosampa.prefeitura.sp.gov.br/')
    assert x['native_crs']=='EPSG:31983'
    assert x['requested_crs']=='EPSG:4326'
    assert x['live_schema_observed_at'].startswith('2026-08-23T21:12:27')
assert parcel['canonical_mapping']['official_identifier_field']=='cd_identificador'
assert parcel['canonical_mapping']['land_area_m2_field']=='qt_area_terreno'
assert zoning['canonical_mapping']['zone_code_field']=='cd_zoneamento_perimetro'
assert zoning['canonical_mapping']['zone_name_field']=='tx_zoneamento_perimetro'
assert zoning['law']=='18.177/2024'
assert zoning['law_publication_date']=='2024-07-26'
assert zoning['legal_valid_from'].startswith('2024-07-26T00:00:00-03:00')
assert zoning['legal_efficacy_status']=='PARTIALLY_SUSPENDED_WITHOUT_EXPRESS_REPEAL'
assert 'não podem ser tratadas como universalmente CONFIRMED' in zoning['legal_scope_note']
assert wfs['license']=='CC-BY-SA-4.0' and wfs['license_url'].startswith('https://prefeitura.sp.gov.br/')
plan=json.loads((R/'data/municipality-labs/sao-paulo-validation-plan.json').read_text())
assert plan['source_contract']['parcel_identifier_field']=='cd_identificador'
assert plan['source_contract']['zone_code_field']=='cd_zoneamento_perimetro'
assert plan['source_contract']['legal_scope_review_required'] is True
assert plan['minimum_cases']>=10
print('v19 Sao Paulo live schema/canonical mapping OK')
