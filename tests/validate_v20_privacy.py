from pathlib import Path

root=Path(__file__).resolve().parents[1]
required=[
 root/'db/platform/migrations/210_v20_privacy_lgpd_operational.sql',
 root/'db/platform/migrations/211_v20_privacy_lgpd_guards.sql',
 root/'db/platform/migrations/212_v20_privacy_retention_seed.sql',
 root/'services/platform-api/src/privacy/privacy-v20.controller.ts',
 root/'services/platform-api/src/privacy/privacy.module.ts',
 root/'services/platform-api/src/auth.service.ts',
 root/'services/platform-api/src/app.module.ts',
 root/'ops/privacy/runtime-integration.sh',
]
for p in required: assert p.exists(),p
sql='\n'.join(p.read_text() for p in required[:3])
for token in [
 'privacy.subject_request','privacy.legal_hold','privacy.retention_policy','privacy.operation_event',
 "request_type IN ('ACCESS','PORTABILITY','RECTIFICATION','RESTRICTION','ERASURE')",
 'FORCE ROW LEVEL SECURITY','privacy.has_active_hold','privacy_erasure_blocked_by_legal_hold',
 'privacy_terminal_request_is_immutable','privacy_operation_event_is_append_only',
 'privacy_protected_class_must_be_retain_nonautomatic','AUDIT_TRAIL','LEGAL_EVIDENCE','SOURCE_PROVENANCE',
 "automatic_execution boolean NOT NULL DEFAULT false",'privacy.seed_default_retention_policies',
 'organization_default_privacy_retention','data_lineage_and_regulatory_evidence'
]: assert token in sql,token
controller=required[3].read_text()
for token in [
 "@Controller('api/v1/privacy/v20')", "@Post('requests')", "@Get('me/export')",
 "@Post('requests/:id/verify')", "@Post('requests/:id/decision')", "@Post('requests/:id/execute')",
 "@Post('legal-holds')", "@Post('legal-holds/:id/release')", "@Put('retention-policies/:category')",
 'privacy_erasure_blocked_by_legal_hold','sessionsRevoked','IDENTITY_PROVIDER_REVIEW',
 "preservedClasses:['AUDIT_TRAIL','LEGAL_EVIDENCE','SOURCE_PROVENANCE']"
]: assert token in controller,token
auth=required[5].read_text();assert 'async logoutUser(userId:string)' in auth
module=required[4].read_text();assert 'PrivacyV20Controller' in module
app=required[6].read_text();assert 'PrivacyModule' in app
print('v20 privacy/LGPD implementation gate OK')
