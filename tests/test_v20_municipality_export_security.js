const fs=require('fs');
const path=require('path');
const assert=require('assert');
const root=path.resolve(__dirname,'..');

const materialize=fs.readFileSync(path.join(root,'db/platform/migrations/202_v20_municipality_materialized_export.sql'),'utf8');
for(const token of ['municipality.export_chunk','materialized_at','bundle_sha256','require_materialized_export_for_offboarding','materialized_ready_export_required_before_offboarding','FORCE ROW LEVEL SECURITY'])assert(materialize.includes(token),token);
const legacy=fs.readFileSync(path.join(root,'db/platform/migrations/203_v20_municipality_legacy_rls.sql'),'utf8');
for(const token of ['municipality.document','municipality.rule_review','municipality.ctm_parcel','municipality.iptu_record','FORCE ROW LEVEL SECURITY',"current_setting('app.tenant_id',true)"])assert(legacy.includes(token),token);
const publication=fs.readFileSync(path.join(root,'db/platform/migrations/204_v20_municipality_publication_guard.sql'),'utf8');assert(publication.includes('rollback_requires_previously_published_snapshot'));
const provenance=fs.readFileSync(path.join(root,'db/platform/migrations/205_v20_municipality_iptu_provenance.sql'),'utf8');assert(provenance.includes('municipality.iptu_record ADD COLUMN IF NOT EXISTS source_snapshot_id'));
const publicPolicy=fs.readFileSync(path.join(root,'db/platform/migrations/206_v20_municipality_open_records_policy.sql'),'utf8');for(const token of ['open_ctm_read','open_pgv_read','open_iptu_read','open_itbi_read',"s.status='PUBLISHED'", "d.visibility='OPEN'", "d.status='ACTIVE'"])assert(publicPolicy.includes(token),token);

const controller=fs.readFileSync(path.join(root,'services/platform-api/src/municipality/municipality-export-v20.controller.ts'),'utf8');
for(const token of ["@Post('exports')",'exports/:id/materialize','municipality.export_chunk','bundle_sha256','record_count','EXPORT_MATERIALIZED','exports/:id/data',"@Post('offboarding')",'materialized_ready_export_required_before_offboarding','offboarding_requires_second_actor',"@Post('offboarding/:id/complete')"])assert(controller.includes(token),token);
for(const forbidden of ['password_hash','access_token','refresh_token','provider_secret_ref'])assert(!controller.includes(forbidden),`export_must_not_include_${forbidden}`);
assert(!controller.includes('select * from core.file_object'),'export_must_not_materialize_file_credentials');

const moduleSrc=fs.readFileSync(path.join(root,'services/platform-api/src/municipality/municipality.module.ts'),'utf8');assert(moduleSrc.includes('MunicipalityExportV20Controller'));assert(moduleSrc.includes('MunicipalityOpenDataV20Controller'));
const open=fs.readFileSync(path.join(root,'services/platform-api/src/municipality/municipality-open-v20.controller.ts'),'utf8');
for(const token of ["d.visibility='OPEN'","d.status='ACTIVE'","s.status='PUBLISHED'",'snapshot_status','datasets/:code/records','source_snapshot_id=$2'])assert(open.includes(token),token);
console.log('v20 Prefeitura export/open-data security gate OK');
