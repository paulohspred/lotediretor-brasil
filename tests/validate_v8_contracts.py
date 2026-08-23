from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
checks={
 'version_v8':(ROOT/'VERSION').read_text().strip()=='v8',
 'v7_kept':(ROOT/'db/platform/migrations/100_v7_70_percent.sql').exists(),
 'runtime_smoke':(ROOT/'ops/runtime/smoke.sh').exists(),
 'rls_isolation_drill':"RLS tenant isolation PASS" in (ROOT/'ops/rls/tenant-isolation.sql').read_text(),
 'backup_database_dumps':'pg_dump -Fc' in (ROOT/'ops/backup/backup.sh').read_text(),
 'restore_drill':'pg_restore' in (ROOT/'ops/backup/restore-drill.sh').read_text(),
 'backup_integrity':'sha256sum -c' in (ROOT/'ops/backup/restore-drill.sh').read_text(),
 'prometheus':(ROOT/'infra/prometheus/prometheus.yml').exists() and 'prometheus:' in (ROOT/'docker-compose.yml').read_text(),
 'grafana':(ROOT/'infra/grafana/provisioning/datasources/prometheus.yml').exists() and 'grafana:' in (ROOT/'docker-compose.yml').read_text(),
 'platform_metrics':(ROOT/'services/platform-api/src/v8.metrics.controller.ts').exists(),
 'control_metrics':(ROOT/'services/control-api/src/v8.metrics.controller.ts').exists(),
 'solar_metrics':"@app.get('/metrics'" in (ROOT/'services/solar-engine/app/main.py').read_text(),
 'aitec_metrics':"@app.get('/metrics'" in (ROOT/'services/aitec-engine/app/main.py').read_text(),
 'wfs_connector':"mode=='WFS'" in (ROOT/'workers/data-pipelines/connectors.py').read_text(),
 'arcgis_connector':"mode=='ARCGIS_GEOJSON'" in (ROOT/'workers/data-pipelines/connectors.py').read_text(),
 'no_fake_source_urls':'example.test' not in (ROOT/'data/sources/catalog.json').read_text(),
}
print(json.dumps(checks,ensure_ascii=False,indent=2))
failed=[k for k,v in checks.items() if not v]
if failed:print('FAILED:',','.join(failed),file=sys.stderr);sys.exit(1)
