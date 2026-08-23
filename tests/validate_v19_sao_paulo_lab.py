import json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
d=json.loads((R/'data/municipality-labs/sao-paulo-3550308.json').read_text())
assert d['municipality_ibge']=='3550308'
assert d['status']=='CORE_LAYERS_MAPPED_PENDING_RUNTIME_SYNC'
wfs=next(x for x in d['sources'] if x['code']=='SP_GEOSAMPA_WFS')
by={x['code']:x for x in wfs['datasets']}
assert by['PARCEL']['typename']=='geoportal:lote_cidadao'
assert by['ZONEAMENTO']['typename']=='geoportal:perimetro_zona_lei_18177_24'
for code in ('PARCEL','ZONEAMENTO'):
    x=by[code];assert x['status']=='MAPPED_PENDING_INGESTION';assert x['metadata_url'].startswith('https://metadados.geosampa.prefeitura.sp.gov.br/');assert x['native_crs']=='EPSG:31983'
assert wfs['license']=='CC-BY-SA-4.0' and wfs['license_url'].startswith('https://prefeitura.sp.gov.br/')
print('v19 Sao Paulo lab core mapping OK')
