from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]

migration=(root/'db/platform/migrations/160_v16_report_property360.sql').read_text()
for token in [
 'CREATE TABLE IF NOT EXISTS report.template(',
 'CREATE TABLE IF NOT EXISTS report.section(',
 'CREATE TABLE IF NOT EXISTS report.evidence(',
 'CREATE TABLE IF NOT EXISTS report.snapshot(',
 'CREATE TABLE IF NOT EXISTS report.share_link(',
 'CREATE TABLE IF NOT EXISTS property360.property_note(',
 'CREATE TABLE IF NOT EXISTS property360.diligence(',
 'CREATE TABLE IF NOT EXISTS municipality.lab_validation_case(',
 "'PROPERTY360_360'"
]: assert token in migration,token
assert migration.count('"code":')>=20

app=(root/'services/platform-api/src/app.module.ts').read_text()
assert 'Property360Module' in app and 'ReportModule' in app
prop=(root/'services/platform-api/src/property360/property360.controller.ts').read_text()
for route in ["@Post('properties/from-analysis')","@Get('properties/:id/ficha')","@Post('properties/:id/notes')","@Post('diligences')"]: assert route in prop,route
report=(root/'services/platform-api/src/report/report.controller.ts').read_text()
for route in ["@Get(':id/manifest')","@Get(':id/sections')","@Post(':id/share')","@Post(':id/share/:shareId/revoke')"]: assert route in report,route
core=(root/'services/platform-api/src/core.module.ts').read_text()
assert "'report.create.v" in core
assert 'PROPERTY360_360' in core
assert 'median-price-m2-v16' in core
worker=(root/'workers/reports/main.py').read_text()
assert "WORKER_VERSION='" in worker and 'build_report' in worker
for token in ['build_report','render_structured','report.snapshot','application/json','report.completed']: assert token in worker,token
builder=(root/'workers/reports/builder.py').read_text()
for token in ['report-360-v1','confidenceSummary','SECTION_DOMAIN','legal.conflict','analysis.spatial_relation']: assert token in builder,token
renderer=(root/'workers/reports/renderer.py').read_text()
for token in ['ParcelSketch','STATUS_COLORS','render_structured']: assert token in renderer,token
catalog=(root/'services/platform-api/src/contracts/route-catalog.ts').read_text()
for path in ['/api/v1/reports/{id}/manifest','/api/v1/property360/properties/{id}/ficha','/api/v1/property360/diligences','/api/v1/municipality-labs/{ibge}/validation-cases']: assert path in catalog,path
plan=json.loads((root/'data/municipality-labs/sao-paulo-validation-plan.json').read_text())
assert plan['municipality_ibge']=='3550308' and plan['cases']==[] and plan['minimum_cases']>=10
assert int((root/'VERSION').read_text().strip().split('.')[0])>=16
assert int(json.loads((root/'package.json').read_text())['version'].split('.')[0])>=16
print('v16 report/property360 contracts OK')
