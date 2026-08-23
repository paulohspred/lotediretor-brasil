from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]

migration=(root/'db/platform/migrations/170_v17_rural360.sql').read_text()
for token in [
 'CREATE TABLE IF NOT EXISTS rural.registry_identifier(',
 'CREATE TABLE IF NOT EXISTS rural.geometry_version(',
 'CREATE TABLE IF NOT EXISTS rural.identity_link(',
 'CREATE TABLE IF NOT EXISTS rural.party_entity(',
 'CREATE TABLE IF NOT EXISTS rural.monitor_checkpoint(',
 'CREATE TABLE IF NOT EXISTS rural.export_job(',
 "'RURAL360_360'",
 "INSERT INTO source.registry(code,title,authority,access_class", "('SNCR'", "('CIB'", "('SICOR'", "('FUNAI_TI'", "('CNUC'",
 'rural_registry_record_visibility','rural_overlap_tenant','rural_identifier_write','rural_geometry_write'
]: assert token in migration, token

app=(root/'services/platform-api/src/app.module.ts').read_text();assert 'RuralModule' in app
controller=(root/'services/platform-api/src/rural/rural.controller.ts').read_text()
for route in ["@Get('search')","@Get('assets/:id/identity-graph')","@Post('assets/:id/identity-graph/rebuild')","@Post('assets/:id/monitors/:monitorId/check')","@Post('assets/:id/exports')","@Post('assets/:id/report')","@Post('identity-links/:linkId/review')"]: assert route in controller,route
for invariant in ['REDACTED_BY_DEFAULT','CPF/CNPJ bruto não pode ser salvo','[RESTRICTED]','CANDIDATE','source.publication','municipality_boundary','withIdempotency','rural.export.queued','rural360.report']:
    assert invariant in controller,invariant
core=(root/'services/platform-api/src/core.module.ts').read_text()
assert 'sourceSnapshotId obrigatório para registro oficial' in core
assert 'snapshot_source_mismatch' in core
assert 'sensitive_attributes_require_authorized_connector' in core
assert 'tenant_owned_asset_required' in core
assert "'source_kind','OFFICIAL_LAYER'" in core
assert "source.publication p where p.status='ACTIVE'" in core

builder=(root/'workers/reports/builder.py').read_text();assert 'build_rural_report' in builder and "report_run['subject_type'] == 'rural_asset'" in builder and 'rural-360-v1' in builder
for token in ["identifier_type in ('CPF','CNPJ')",'historical_snapshot','licenseTerms','snapshots válidos na data-base']:
    assert token in builder,token
renderer=(root/'workers/reports/renderer.py').read_text();
for code in ['rural_cover','rural_identity','rural_registries','rural_environment','rural_monitoring','rural_evidence']:assert code in renderer,code
current=(root/'VERSION').read_text().strip(); worker=(root/'workers/rural-export/main.py').read_text();assert f"VERSION='{current}'" in worker and 'rural.export.completed' in worker
assert (root/'workers/rural-export/Dockerfile').exists()
compose=(root/'docker-compose.yml').read_text();assert 'rural-export-worker:' in compose
catalog=(root/'services/platform-api/src/contracts/route-catalog.ts').read_text()
for path in ['/api/v1/rural/search','/api/v1/rural/assets/{id}/identity-graph','/api/v1/rural/assets/{id}/exports','/api/v1/rural/assets/{id}/report']:assert path in catalog,path
graphql=(root/'services/platform-api/src/graphql.ts').read_text();assert 'RuralAssetSummary' in graphql and 'ruralAssets' in graphql
ui=(root/'apps/client-web/components/workspaces/RuralWorkspace.tsx').read_text();assert 'RE Rural 360' in ui and 'identity graph' in ui and 'Exportar KMZ' in ui
assert json.loads((root/'package.json').read_text())['version']==current
print('v17 rural360 contracts OK')
