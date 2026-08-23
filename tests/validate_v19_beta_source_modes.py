import json
from pathlib import Path
cat=json.loads(Path('data/sources/catalog.json').read_text())
by={x['code']:x for x in cat['sources']}
assert by['IBGE_LOCALIDADES']['integration']=='ACTIVE_ADAPTER'
assert by['IBAMA_EMBARGO']['adapterMode']=='CKAN_SHP_ZIP_GDAL'
assert by['IBAMA_EMBARGO']['accessClass']=='A'
assert by['PRODES']['wfsBase'].startswith('https://terrabrasilis.dpi.inpe.br/geoserver/')
assert by['PRODES']['integration']=='WFS_ADAPTER_READY_TYPENAME_NOT_PINNED'
assert by['SIGEF']['accessClass']=='C'
assert 'CONTECTA' not in json.dumps(by['SIGEF']).upper()
assert by['SIGEF']['integration']=='OFFICIAL_API_IDENTIFIED_REQUIRES_CONECTA_CREDENTIALS'
contracts=json.loads(Path('data/contracts/official-sources-v19-beta.json').read_text())
assert contracts['version']==19
assert contracts['sources']['SIGEF']['credentialsRequired'] is True
pre=Path('ops/data/source-preflight.py').read_text()
for token in ['SIGEF','Conecta','CKAN_SHP_ZIP_GDAL','GetCapabilities']:
    assert token in pre,token
connectors=Path('workers/data-pipelines/connectors.py').read_text()
assert "code=='SIGEF'" not in connectors
assert 'epsg4326_coordinate_range' in connectors
print('v19-beta national source access/mode contracts OK')
