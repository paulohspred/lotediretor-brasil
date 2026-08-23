from __future__ import annotations
import os,sys,requests

SOURCES={
  'CAR':'GEOJSON',
  'IBAMA_EMBARGO':'CKAN_SHP_ZIP_GDAL',
  'PRODES':'WFS',
}
failed=[]
for code,default_mode in SOURCES.items():
    if os.getenv(f'{code}_SOURCE_ENABLED','false').lower() not in {'1','true','yes'}:
        print('SKIP',code,'disabled');continue
    url=os.getenv(f'{code}_SOURCE_URL','').strip();mode=os.getenv(f'{code}_SOURCE_MODE',default_mode).strip().upper();lic=os.getenv(f'{code}_SOURCE_LICENSE_URL','').strip()
    if not url or not lic: failed.append(f'{code}: URL/license required');continue
    try:
        if mode=='WFS':
            r=requests.get(url,params={'service':'WFS','request':'GetCapabilities','version':'2.0.0'},timeout=45);r.raise_for_status()
            if not os.getenv(f'{code}_SOURCE_TYPENAME','').strip(): failed.append(f'{code}: WFS typeName must be pinned/versioned')
        elif mode=='CKAN_SHP_ZIP_GDAL':
            r=requests.get(url,timeout=45);r.raise_for_status();payload=r.json()
            resources=((payload.get('result') or {}).get('resources') or []) if isinstance(payload,dict) else []
            if not any('SHP' in str(x.get('format','')).upper() or str(x.get('url','')).lower().endswith('.zip') for x in resources):failed.append(f'{code}: CKAN package has no SHP/ZIP resource')
        elif mode in {'GEOJSON','ARCGIS_GEOJSON'}:
            r=requests.get(url,timeout=45);r.raise_for_status()
        else:failed.append(f'{code}: unsupported preflight mode {mode}');continue
        print('PASS',code,mode,r.status_code)
    except Exception as e: failed.append(f'{code}: {e}')

# SIGEF/Conecta is intentionally a separate authenticated integration, not a
# generic geospatial connector.
if os.getenv('SIGEF_SOURCE_ENABLED','false').lower() in {'1','true','yes'}:
    if not os.getenv('SIGEF_CONECTA_BEARER','').strip():failed.append('SIGEF: Conecta bearer/credential required; generic SOURCE_URL activation is forbidden')
    else:print('PASS SIGEF credential configured; runtime API contract validation still required')

if failed:
    print('\n'.join('FAIL '+x for x in failed),file=sys.stderr);sys.exit(1)
