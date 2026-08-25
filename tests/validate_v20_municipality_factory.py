from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
required=[
 root/'db/platform/migrations/207_v20_municipality_factory.sql',
 root/'db/platform/migrations/208_v20_municipality_factory_guards.sql',
 root/'db/platform/migrations/209_v20_municipality_factory_contracts.sql',
 root/'services/platform-api/src/municipality/municipality-factory.logic.ts',
 root/'services/platform-api/src/municipality/municipality-factory.connector.ts',
 root/'services/platform-api/src/municipality/municipality-factory.controller.ts',
 root/'services/platform-api/src/municipality/municipality.module.ts',
 root/'tests/test_v20_municipality_factory.js',
]
for p in required: assert p.exists(),p
sql='\n'.join(p.read_text() for p in required[:3])
for token in [
 'source.connector_contract','municipality.factory_source','factory_discovery','factory_connector_run',
 'factory_qa_result','factory_rule_candidate','factory_golden_case','factory_golden_run',
 'factory_monitor_event','factory_coverage_snapshot','WFS','WMS','ARCGIS','CKAN','HTML','PDF','ZIP',
 'FORCE ROW LEVEL SECURITY','factory_activation_requires_verified_license',
 'factory_homologation_requires_all_qa_pass','factory_homologation_requires_golden_pass',
 'factory_homologation_requires_professionally_reviewed_golden','candidate_confirmation_requires_human_review',
 'factory_terminal_run_is_immutable','refresh_factory_coverage_snapshot'
]: assert token in sql,token
logic=required[3].read_text()
for token in ['MUNICIPALITY_FACTORY_VERSION','validateFactoryUrl','factory_url_private_or_literal_host_blocked','buildIngestUrl','activationGate','homologationGate','qaFromNormalized','monitorChange','goldenRun']:
 assert token in logic,token
connector=required[4].read_text()
for token in ['redirect:\'manual\'','factory_payload_too_large','fetchPagedGeoJson','PutObjectCommand','municipality-factory/','pinnedConfigFingerprint']:
 assert token in connector,token
controller=required[5].read_text()
for token in [
 "@Controller('api/v1/municipality/v20/factory')", "@Post('sources/:id/discover')", "@Post('sources/:id/activate')",
 "@Post('sources/:id/ingest')", "@Post('sources/:id/snapshots/:snapshotId/qa')", "status,'CANDIDATE'",
 "@Post('sources/:id/goldens/run')", "@Post('sources/:id/homologate')", "@Post('sources/:id/prepare-publication')",
 "@Post('sources/:id/monitor')", "@Get('metrics')", 'factory_homologation_blocked'
]: assert token in controller,token
module=required[6].read_text();assert 'MunicipalityFactoryV20Controller' in module
subprocess.run(['node','tests/test_v20_municipality_factory.js'],check=True)
print('v20 Municipality Factory implementation gate OK')
