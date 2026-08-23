DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lotediretor_event_dispatcher') THEN
    CREATE ROLE lotediretor_event_dispatcher NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS;
  END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS api;
CREATE SCHEMA IF NOT EXISTS event;

CREATE TABLE IF NOT EXISTS api.idempotency_key(
  tenant_id uuid NOT NULL,
  scope text NOT NULL,
  idempotency_key text NOT NULL,
  status text NOT NULL CHECK(status IN ('IN_PROGRESS','COMPLETED')),
  response jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  expires_at timestamptz NOT NULL,
  PRIMARY KEY(tenant_id,scope,idempotency_key)
);
CREATE INDEX IF NOT EXISTS api_idempotency_expiry_idx ON api.idempotency_key(expires_at);

CREATE TABLE IF NOT EXISTS event.outbox(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid,
  topic text NOT NULL,
  aggregate_type text,
  aggregate_id text,
  dedupe_key text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','PUBLISHING','PUBLISHED','FAILED')),
  attempts integer NOT NULL DEFAULT 0,
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz
);
ALTER TABLE event.outbox ADD COLUMN IF NOT EXISTS publish_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
CREATE UNIQUE INDEX IF NOT EXISTS event_outbox_dedupe_ux ON event.outbox(dedupe_key) WHERE dedupe_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS event_outbox_pending_idx ON event.outbox(status,next_attempt_at,created_at) WHERE status IN ('PENDING','FAILED');

CREATE TABLE IF NOT EXISTS event.consumer_checkpoint(
  consumer text NOT NULL,
  event_id uuid NOT NULL,
  processed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(consumer,event_id)
);

GRANT USAGE ON SCHEMA api,event TO lotediretor_app;
GRANT CONNECT ON DATABASE lotediretor TO lotediretor_event_dispatcher;
GRANT USAGE ON SCHEMA event TO lotediretor_event_dispatcher;
GRANT SELECT,INSERT,UPDATE ON event.outbox TO lotediretor_event_dispatcher;
GRANT SELECT,INSERT ON event.consumer_checkpoint TO lotediretor_event_dispatcher;
GRANT SELECT,INSERT,UPDATE,DELETE ON api.idempotency_key TO lotediretor_app;
GRANT SELECT,INSERT,UPDATE ON event.outbox TO lotediretor_app;
GRANT SELECT,INSERT ON event.consumer_checkpoint TO lotediretor_app;

-- Outbox rows containing tenant-scoped payloads inherit application isolation.
ALTER TABLE event.outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE event.outbox FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS event_outbox_tenant_policy ON event.outbox;
CREATE POLICY event_outbox_tenant_policy ON event.outbox
USING (tenant_id IS NULL OR tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK (tenant_id IS NULL OR tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);

-- Background workers need cross-tenant processing but must never own schemas/DDL.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lotediretor_worker') THEN
    CREATE ROLE lotediretor_worker NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS;
  END IF;
END $$;
GRANT CONNECT ON DATABASE lotediretor TO lotediretor_worker;
GRANT USAGE ON SCHEMA iam,core,source,geo,legal,planning,evidence,cadastre,registry,rural,infra,market,property360,crm,condo,municipality,solar,aitec,analysis,report,notification,ingest,data_quality,api,event TO lotediretor_worker;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA iam,core,source,geo,legal,planning,evidence,cadastre,registry,rural,infra,market,property360,crm,condo,municipality,solar,aitec,analysis,report,notification,ingest,data_quality,api,event TO lotediretor_worker;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA iam,core,source,geo,legal,planning,evidence,cadastre,registry,rural,infra,market,property360,crm,condo,municipality,solar,aitec,analysis,report,notification,ingest,data_quality,api,event TO lotediretor_worker;

ALTER TABLE api.idempotency_key ENABLE ROW LEVEL SECURITY;
ALTER TABLE api.idempotency_key FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS api_idempotency_tenant_policy ON api.idempotency_key;
CREATE POLICY api_idempotency_tenant_policy ON api.idempotency_key FOR ALL TO lotediretor_app
USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);

-- v14: public-or-tenant datasets. Official/public rows are stored with tenant_id NULL;
-- private overlays remain visible only to the active tenant. These policies repair the
-- overly strict generic tenant policy used by earlier recovery migrations.
DO $$
DECLARE item record;
BEGIN
  FOR item IN SELECT * FROM (VALUES
    ('geo','parcel'),
    ('legal','document'),
    ('property360','comparable'),
    ('rural','asset'),
    ('property360','market_snapshot'),
    ('solar','tariff_snapshot')
  ) AS x(schemaname,tablename)
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',item.schemaname,item.tablename);
    EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',item.schemaname,item.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I.%I',item.schemaname,item.tablename);
    EXECUTE format('DROP POLICY IF EXISTS shared_or_tenant_visibility ON %I.%I',item.schemaname,item.tablename);
    EXECUTE format('DROP POLICY IF EXISTS market_snapshot_visibility ON %I.%I',item.schemaname,item.tablename);
    EXECUTE format(
      'CREATE POLICY shared_or_tenant_visibility ON %I.%I FOR SELECT TO lotediretor_app USING (tenant_id IS NULL OR tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',
      item.schemaname,item.tablename
    );
    EXECUTE format(
      'CREATE POLICY tenant_write ON %I.%I FOR INSERT TO lotediretor_app WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',
      item.schemaname,item.tablename
    );
    EXECUTE format(
      'CREATE POLICY tenant_update ON %I.%I FOR UPDATE TO lotediretor_app USING (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',
      item.schemaname,item.tablename
    );
    EXECUTE format(
      'CREATE POLICY tenant_delete ON %I.%I FOR DELETE TO lotediretor_app USING (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',
      item.schemaname,item.tablename
    );
  END LOOP;
END $$;

-- Municipality workspace itself is tenant-owned via organization_id rather than tenant_id.
ALTER TABLE municipality.tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE municipality.tenant FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS municipality_tenant_isolation ON municipality.tenant;
CREATE POLICY municipality_tenant_isolation ON municipality.tenant FOR ALL TO lotediretor_app
USING (organization_id = nullif(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK (organization_id = nullif(current_setting('app.tenant_id',true),'')::uuid);

-- Municipality child policies depend on municipality.tenant and therefore also require
-- the tenant setting. FORCE prevents future owner-like service accounts from bypassing them.
ALTER TABLE municipality.document FORCE ROW LEVEL SECURITY;
ALTER TABLE municipality.ctm_parcel FORCE ROW LEVEL SECURITY;
ALTER TABLE municipality.iptu_record FORCE ROW LEVEL SECURITY;
ALTER TABLE municipality.rule_review FORCE ROW LEVEL SECURITY;

-- File/ingest rows are private tenant data and should also be forced even though they live
-- outside the schemas covered by the generic v9 hardening loop.
ALTER TABLE core.file_object FORCE ROW LEVEL SECURITY;
ALTER TABLE ingest.document_job FORCE ROW LEVEL SECURITY;
ALTER TABLE ingest.document_text FORCE ROW LEVEL SECURITY;
