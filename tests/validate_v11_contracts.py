from pathlib import Path
import json,sys
R=Path(__file__).resolve().parents[1];c=(R/'workers/data-pipelines/connectors.py').read_text();e=(R/'.env.example').read_text()
checks={'version_v11':(R/'VERSION').read_text().strip()=='v11','gdal_image':'gdal-bin' in (R/'workers/data-pipelines/Dockerfile').read_text(),'ckan_shp':'CKAN_SHP_ZIP_GDAL' in c,'license_gate':'license/access terms URL is required' in c,'explicit_activation':'SOURCE_ENABLED' in c,'ibama_official_ckan':'dadosabertos.ibama.gov.br/api/3/action/package_show?id=termos-de-embargo' in e,'source_preflight':(R/'ops/data/source-preflight.py').exists()}
print(json.dumps(checks,indent=2));bad=[k for k,v in checks.items() if not v]
if bad:print('FAILED',bad,file=sys.stderr);sys.exit(1)
