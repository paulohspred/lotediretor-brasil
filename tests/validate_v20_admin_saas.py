from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
required=[
    root/'db/control/migrations/200_v20_admin_saas_operational.sql',
    root/'db/control/migrations/201_v20_admin_saas_analytics.sql',
    root/'db/control/migrations/202_v20_admin_append_only_replay.sql',
    root/'services/control-api/src/v20-admin-logic.ts',
    root/'services/control-api/src/v20-admin.controller.ts',
    root/'services/control-api/src/v20.module.ts',
    root/'ops/rls/runtime-isolation.sh',
    root/'ops/backup/backup.sh',
    root/'ops/backup/restore-drill.sh',
]
for p in required:
    assert p.exists(),p
migration='\n'.join(p.read_text() for p in required[:3])
for token in ['dunning_case','billing.adjustment','payment_allocation','nfse_document','support_session','impersonation_event','form_submission','funnel_definition','experiment_assignment','usage_cost','rollback_event','backup_run','restore_run','dr_drill','FORCE ROW LEVEL SECURITY']:
    assert token in migration,token
controller=required[4].read_text()
for token in ['Idempotency-Key'.lower().replace('-','_') if False else 'idempotency_key_required','support/sessions','billing/payments/:paymentId/refunds','billing/payments/:paymentId/chargebacks','billing/tenants/:tenantId/reconcile','fiscal/nfse','analytics/funnels','analytics/experiments','product/feature-flags','release/rollbacks','ops/dashboard']:
    assert token in controller,token
subprocess.run(['node','tests/test_v20_admin_saas.js'],cwd=root,check=True)
print('v20 Admin SaaS operational implementation gate OK')
