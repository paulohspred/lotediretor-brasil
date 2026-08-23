from pathlib import Path
import os,sys,json
required=['OIDC_CLIENT_SECRET','PUBLIC_DOMAIN']
for k in required:
 v=os.getenv(k,'')
 if not v or 'change-me' in v or v.endswith('.invalid'): print(f'FAIL {k}',file=sys.stderr);sys.exit(1)
src=Path('infra/keycloak/templates/realm-lotediretor.production.json').read_text()
src=src.replace('__OIDC_CLIENT_SECRET__',os.environ['OIDC_CLIENT_SECRET']).replace('__PUBLIC_DOMAIN__',os.environ['PUBLIC_DOMAIN'])
data=json.loads(src)
if data.get('users'): raise SystemExit('production realm must not contain imported users')
out=Path('infra/keycloak/generated/realm-lotediretor.production.json');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print(out)
