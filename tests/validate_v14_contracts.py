from pathlib import Path
import json,re,sys,yaml
R=Path(__file__).resolve().parents[1]
core=(R/'services/platform-api/src/core.module.ts').read_text()
v7=(R/'services/platform-api/src/v7.controller.ts').read_text()
gql=(R/'services/platform-api/src/graphql.ts').read_text()
jobs=(R/'services/platform-api/src/jobs/job-events.controller.ts').read_text()
main=(R/'services/platform-api/src/main.ts').read_text()
control_main=(R/'services/control-api/src/main.ts').read_text()
migration=(R/'db/platform/migrations/140_v14_contracts_events.sql').read_text()
compose=yaml.safe_load((R/'docker-compose.yml').read_text())
prod=yaml.safe_load((R/'docker-compose.production.yml').read_text())
dispatcher=(R/'services/event-dispatcher/src/main.ts').read_text()
route_catalog=(R/'services/platform-api/src/contracts/route-catalog.ts').read_text()
openapi=(R/'services/platform-api/src/contracts/openapi.controller.ts').read_text()
checks={
 'version_v14':(R/'VERSION').read_text().strip()=='v14',
 'package_v14':json.loads((R/'package.json').read_text()).get('version')=='14.0.0',
 'app_boundaries':all(x in (R/'services/platform-api/src/app.module.ts').read_text() for x in ['CoreModule','DomainsModule','ContractsModule','JobEventsModule']),
 'tenant_helper':(R/'services/platform-api/src/common/tenant-db.ts').exists() and "set_config('app.tenant_id'" in (R/'services/platform-api/src/common/tenant-db.ts').read_text(),
 'rest_tenant_context':'tenantQuery(pool,session.organizationId' in core and 'tenantTx(pool,session.organizationId' in core,
 'graphql_tenant_context':'tenantQuery(pool,s.organizationId' in gql and 'tenantTx(pool,s.organizationId' in gql,
 'sse_tenant_context':'tenantTx(pool,tenantId' in jobs,
 'global_error_filter':'ApiExceptionFilter' in main and 'ApiExceptionFilter' in control_main,
 'trace_headers':'x-trace-id' in main and 'x-request-id' in main,
 'openapi':'openapi.json' in openapi and "openapi:'3.1.0'" in openapi,
 'graphql_surface':all(x in gql for x in ['properties','developments','comparables','sourceCoverage','analysisFindings']),
 'sse_jobs':"events/jobs/:id" in jobs and '@Sse' in jobs,
 'idempotency_schema':'api.idempotency_key' in migration and 'FORCE ROW LEVEL SECURITY' in migration,
 'idempotent_commands':all(x in core for x in ["'analysis.run'","'report.create'","'property360.avm'","'rural.overlaps.recalculate'"]),
 'outbox_schema':'event.outbox' in migration and 'publish_metadata' in migration,
 'jetstream_ack':all(x in dispatcher for x in ['jetstreamManager','LOTEDIRETOR_EVENTS','msgID','ack.stream','ack.seq']),
 'outbox_events':all(x in core for x in ['source.snapshot.published','analysis.completed','report.queued','document.queued']),
 'migration_services':all(x in compose['services'] for x in ['platform-migrate','control-migrate','platform-db-role-init']),
 'migration_before_roles':compose['services']['platform-db-role-init']['depends_on']['platform-migrate']['condition']=='service_completed_successfully' and compose['services']['platform-db-role-init']['depends_on']['control-migrate']['condition']=='service_completed_successfully',
 'api_runtime_nonowner':'lotediretor_app' in str(compose['services']['platform-api']['environment']['PLATFORM_DATABASE_URL']),
 'worker_nonowner':'lotediretor_worker' in str(compose['services']['document-worker']['environment']['PLATFORM_DATABASE_URL']) and 'lotediretor_worker' in str(compose['services']['report-worker']['environment']['PLATFORM_DATABASE_URL']),
 'event_role':'lotediretor_event_dispatcher' in str(compose['services']['event-dispatcher']['environment']['PLATFORM_EVENT_DATABASE_URL']),
 'shared_visibility':all(x in migration for x in ["('geo','parcel')","('legal','document')","('property360','comparable')","('rural','asset')",'shared_or_tenant_visibility']),
 'municipality_rls':'municipality_tenant_isolation' in migration and 'ALTER TABLE municipality.tenant FORCE ROW LEVEL SECURITY' in migration,
 'no_workspace_hijack':'set organization_id=excluded.organization_id' not in core,
 'prod_worker_secrets':all(k in (R/'.env.production.example').read_text() for k in ['PLATFORM_DB_EVENT_PASSWORD','PLATFORM_DB_WORKER_PASSWORD','CONTROL_DB_WORKER_PASSWORD']),
 'docs':all((R/x).exists() for x in ['docs/architecture/V14_BOUNDARIES.md','docs/api/API_V14.md','docs/adr/ADR-013-transactional-outbox-jetstream.md','docs/adr/ADR-014-runtime-roles-and-tenant-context.md']),
}
# Static guard: no direct pool.query against known private RLS tables in user-facing REST/GraphQL/SSE.
private_patterns=['property360.property','property360.development','property360.avm_run','analysis.run','report.report_run','notification.notification','rural.asset','rural.monitor','rural.overlap_result','condo.condominium','condo.rule','condo.document_chunk','solar.project','solar.scenario','aitec.project','aitec.scenario','core.file_object','ingest.document_job','municipality.rule_review']
viol=[]
for name,text in [('core',core),('domains',v7),('graphql',gql),('jobs',jobs)]:
  for line_no,line in enumerate(text.splitlines(),1):
    if 'pool.query' in line and any(t in line for t in private_patterns):viol.append(f'{name}:{line_no}')
checks['no_direct_private_pool_queries']=not viol
checks['private_query_violations']=viol==[]
print(json.dumps(checks,indent=2,ensure_ascii=False))
bad=[k for k,v in checks.items() if v is not True]
if bad:
 print('FAILED',bad,'violations=',viol,file=sys.stderr);sys.exit(1)
