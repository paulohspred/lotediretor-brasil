from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
required=[
    root/'db/platform/migrations/200_v20_municipality_operational.sql',
    root/'db/platform/migrations/201_v20_municipality_open_data_guard.sql',
    root/'db/platform/migrations/202_v20_municipality_materialized_export.sql',
    root/'db/platform/migrations/203_v20_municipality_legacy_rls.sql',
    root/'db/platform/migrations/204_v20_municipality_publication_guard.sql',
    root/'db/platform/migrations/205_v20_municipality_iptu_provenance.sql',
    root/'db/platform/migrations/206_v20_municipality_open_records_policy.sql',
    root/'services/platform-api/src/municipality/v20-governance.ts',
    root/'services/platform-api/src/municipality/municipality-v20.controller.ts',
    root/'services/platform-api/src/municipality/municipality-open-v20.controller.ts',
    root/'services/platform-api/src/municipality/municipality-export-v20.controller.ts',
    root/'services/platform-api/src/municipality/municipality.module.ts',
]
for p in required:
    assert p.exists(),p
sql='\n'.join(p.read_text() for p in required[:7])
for token in [
    'MUNICIPAL_ADMIN','DATA_STEWARD','CIB_SINTER','publication_event_v20','recalculation_job',
    'licensing_case','audit_event_v20','export_chunk','require_materialized_export_for_offboarding',
    'rollback_requires_previously_published_snapshot','municipality.ctm_parcel','municipality.iptu_record',
    'open_ctm_read','open_pgv_read','open_iptu_read','open_itbi_read','FORCE ROW LEVEL SECURITY'
]:
    assert token in sql,token
main=required[8].read_text()
for token in [
    'onboarding','datasets/:datasetId/publish/:snapshotId','datasets/:datasetId/rollback/:snapshotId',
    'recalculations/enqueue-analysis','recalculations/reconcile','AI_GATEWAY_INTERNAL_URL','sourceSnapshotIds',
    'knowledgeStatuses:[\'CONFIRMED\']','CTM_UPSERT','IPTU_RECORDED','ITBI_RECORDED','licensingDecisionGuard'
]:
    assert token in main,token
export_controller=required[10].read_text()
for token in ['exports/:id/materialize','EXPORT_MATERIALIZED','exports/:id/data','bundle_sha256','offboarding_requires_second_actor','offboarding/:id/complete']:
    assert token in export_controller,token
open_controller=required[9].read_text()
for token in ['datasets/:code/records','source_snapshot_id=$2','openDataProjection']:
    assert token in open_controller,token
subprocess.run(['node','tests/test_v20_municipality_governance.js'],check=True)
subprocess.run(['node','tests/test_v20_municipality_export_security.js'],check=True)
print('v20 Prefeitura operational implementation gate OK')
