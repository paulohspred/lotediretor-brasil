-- v7: operational hardening toward the 70% product milestone.
-- Adds data contracts/quality, Imóvel 360 developments+CRM, richer rural/condo/
-- municipality/solar/A.I TEC persistence, report artifacts and tenant-safe indexes.

CREATE SCHEMA IF NOT EXISTS data_quality;
CREATE SCHEMA IF NOT EXISTS crm;

ALTER TABLE source.snapshot ADD COLUMN IF NOT EXISTS record_count bigint;
ALTER TABLE source.snapshot ADD COLUMN IF NOT EXISTS validation_status text NOT NULL DEFAULT 'PENDING';
ALTER TABLE source.snapshot ADD COLUMN IF NOT EXISTS schema_version text;

CREATE TABLE IF NOT EXISTS source.dataset_contract(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  source_id uuid NOT NULL REFERENCES source.registry(id) ON DELETE CASCADE,
  version text NOT NULL,
  required_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
  geometry_type text,
  srid int,
  primary_keys text[] NOT NULL DEFAULT '{}',
  freshness_hours int,
  license_required boolean NOT NULL DEFAULT true,
  status text NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(source_id,version)
);

CREATE TABLE IF NOT EXISTS data_quality.result(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  source_id uuid NOT NULL REFERENCES source.registry(id),
  snapshot_id uuid NOT NULL REFERENCES source.snapshot(id) ON DELETE CASCADE,
  check_code text NOT NULL,
  severity text NOT NULL CHECK(severity IN ('INFO','WARN','ERROR')),
  status text NOT NULL CHECK(status IN ('PASS','FAIL','SKIP')),
  expected jsonb NOT NULL DEFAULT '{}'::jsonb,
  observed jsonb NOT NULL DEFAULT '{}'::jsonb,
  checked_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(snapshot_id,check_code)
);

CREATE TABLE IF NOT EXISTS source.publication_event(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  source_id uuid NOT NULL REFERENCES source.registry(id),
  municipality_ibge text,
  previous_snapshot_id uuid REFERENCES source.snapshot(id),
  next_snapshot_id uuid NOT NULL REFERENCES source.snapshot(id),
  action text NOT NULL CHECK(action IN ('ACTIVATE','ROLLBACK')),
  actor text NOT NULL,
  reason text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS property360.development(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  name text NOT NULL,
  municipality_ibge text,
  status text NOT NULL DEFAULT 'PROSPECT',
  geom geometry(Geometry,4326),
  gross_land_area_m2 numeric,
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS property360_development_tenant_idx ON property360.development(tenant_id,status,created_at DESC);
CREATE INDEX IF NOT EXISTS property360_development_geom_gix ON property360.development USING gist(geom);

CREATE TABLE IF NOT EXISTS property360.development_parcel(
  development_id uuid NOT NULL REFERENCES property360.development(id) ON DELETE CASCADE,
  parcel_id uuid NOT NULL REFERENCES geo.parcel(id),
  PRIMARY KEY(development_id,parcel_id)
);

CREATE TABLE IF NOT EXISTS crm.lead(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  property_id uuid REFERENCES property360.property(id),
  development_id uuid REFERENCES property360.development(id),
  name text NOT NULL,
  stage text NOT NULL DEFAULT 'NEW',
  score numeric NOT NULL DEFAULT 0,
  owner_user_id text,
  contact jsonb NOT NULL DEFAULT '{}'::jsonb,
  tags text[] NOT NULL DEFAULT '{}',
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS crm_lead_tenant_stage_idx ON crm.lead(tenant_id,stage,score DESC);

CREATE TABLE IF NOT EXISTS property360.market_snapshot(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid,
  municipality_ibge text NOT NULL,
  reference_date date NOT NULL,
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  data_class text NOT NULL DEFAULT 'OBSERVED',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,municipality_ibge,reference_date,source_snapshot_id)
);

CREATE TABLE IF NOT EXISTS rural.layer_catalog(
  code text PRIMARY KEY,
  title text NOT NULL,
  authority text NOT NULL,
  source_id uuid REFERENCES source.registry(id),
  legal_nature text,
  status text NOT NULL DEFAULT 'CONFIGURED',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS rural.layer_feature(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  layer_code text NOT NULL REFERENCES rural.layer_catalog(code),
  source_snapshot_id uuid NOT NULL REFERENCES source.snapshot(id),
  official_identifier text,
  geom geometry(Geometry,4326) NOT NULL,
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  valid_from timestamptz,
  valid_to timestamptz,
  recorded_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rural_layer_feature_geom_gix ON rural.layer_feature USING gist(geom);
CREATE INDEX IF NOT EXISTS rural_layer_feature_lookup_idx ON rural.layer_feature(layer_code,source_snapshot_id);

CREATE TABLE IF NOT EXISTS rural.monitor_event(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  monitor_id uuid NOT NULL REFERENCES rural.monitor(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  status text NOT NULL DEFAULT 'NEW',
  before_snapshot_id uuid REFERENCES source.snapshot(id),
  after_snapshot_id uuid REFERENCES source.snapshot(id),
  change_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  detected_at timestamptz NOT NULL DEFAULT now(),
  acknowledged_at timestamptz
);

CREATE TABLE IF NOT EXISTS condo.meeting(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  meeting_date date NOT NULL,
  kind text NOT NULL DEFAULT 'ASSEMBLY',
  title text NOT NULL,
  document_id uuid REFERENCES condo.document(id),
  decisions jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS condo.evidence_link(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  rule_id uuid REFERENCES condo.rule(id) ON DELETE CASCADE,
  document_id uuid REFERENCES condo.document(id) ON DELETE CASCADE,
  chunk_id uuid REFERENCES condo.document_chunk(id) ON DELETE CASCADE,
  locator text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS municipality.ctm_import(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL,
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  filename text,
  sha256 text,
  status text NOT NULL DEFAULT 'QUEUED',
  records_received bigint NOT NULL DEFAULT 0,
  records_loaded bigint NOT NULL DEFAULT 0,
  errors jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS municipality.publication_event(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL,
  publication_id uuid REFERENCES municipality.publication(id),
  action text NOT NULL,
  actor text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS solar.tariff_snapshot(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid,
  distributor text NOT NULL,
  municipality_ibge text,
  reference_date date NOT NULL,
  tariff_brl_per_kwh numeric NOT NULL CHECK(tariff_brl_per_kwh > 0),
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  assumptions jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS solar.simulation_run(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL REFERENCES solar.project(id) ON DELETE CASCADE,
  scenario_id uuid REFERENCES solar.scenario(id) ON DELETE SET NULL,
  engine_version text NOT NULL,
  status text NOT NULL,
  input_snapshot jsonb NOT NULL,
  output_snapshot jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE aitec.scenario ALTER COLUMN constraint_snapshot_id DROP NOT NULL;
CREATE TABLE IF NOT EXISTS aitec.scenario_metric(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  scenario_id uuid NOT NULL REFERENCES aitec.scenario(id) ON DELETE CASCADE,
  metric_code text NOT NULL,
  value_numeric numeric,
  value_text text,
  unit text,
  status text NOT NULL DEFAULT 'CALCULATED',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(scenario_id,metric_code)
);

CREATE TABLE IF NOT EXISTS aitec.artifact(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  scenario_id uuid NOT NULL REFERENCES aitec.scenario(id) ON DELETE CASCADE,
  kind text NOT NULL,
  object_key text,
  content_type text,
  sha256 text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS report.artifact(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  report_run_id uuid NOT NULL REFERENCES report.report_run(id) ON DELETE CASCADE,
  object_key text NOT NULL,
  content_type text NOT NULL DEFAULT 'application/pdf',
  size_bytes bigint,
  sha256 text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(report_run_id,sha256)
);

CREATE INDEX IF NOT EXISTS report_run_tenant_status_idx ON report.report_run(tenant_id,status,created_at DESC);
CREATE INDEX IF NOT EXISTS notification_tenant_status_idx ON notification.notification(tenant_id,status,created_at DESC);
CREATE INDEX IF NOT EXISTS analysis_run_tenant_date_idx ON analysis.run(tenant_id,base_date DESC,created_at DESC);

-- Tenant policies for the new tenant-owned tables. They are effective when the API
-- connects through a non-owner role and sets app.tenant_id per request/transaction.
DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT * FROM (VALUES
    ('property360','development'),('crm','lead'),('rural','monitor_event'),
    ('condo','meeting'),('condo','evidence_link'),('municipality','ctm_import'),
    ('municipality','publication_event'),('solar','simulation_run'),
    ('aitec','scenario_metric'),('aitec','artifact'),('report','artifact')
  ) AS x(schemaname,tablename)
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I.%I',r.schemaname,r.tablename);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I.%I USING (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',r.schemaname,r.tablename);
  END LOOP;
END $$;

-- Public/tenant market data: global licensed observations can be tenant_id NULL.
ALTER TABLE property360.market_snapshot ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS market_snapshot_visibility ON property360.market_snapshot;
CREATE POLICY market_snapshot_visibility ON property360.market_snapshot
USING (tenant_id IS NULL OR tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid);

-- Existing municipality-owned tables receive isolation through their workspace owner.
ALTER TABLE municipality.document ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS municipality_document_isolation ON municipality.document;
CREATE POLICY municipality_document_isolation ON municipality.document USING (
  EXISTS (SELECT 1 FROM municipality.tenant mt
          WHERE mt.id=municipality.document.municipality_tenant_id
            AND mt.organization_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
);

ALTER TABLE municipality.ctm_parcel ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS municipality_ctm_isolation ON municipality.ctm_parcel;
CREATE POLICY municipality_ctm_isolation ON municipality.ctm_parcel USING (
  EXISTS (SELECT 1 FROM municipality.tenant mt
          WHERE mt.id=municipality.ctm_parcel.municipality_tenant_id
            AND mt.organization_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
);

ALTER TABLE municipality.iptu_record ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS municipality_iptu_isolation ON municipality.iptu_record;
CREATE POLICY municipality_iptu_isolation ON municipality.iptu_record USING (
  EXISTS (SELECT 1 FROM municipality.tenant mt
          WHERE mt.id=municipality.iptu_record.municipality_tenant_id
            AND mt.organization_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
);

ALTER TABLE municipality.rule_review ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS municipality_review_isolation ON municipality.rule_review;
CREATE POLICY municipality_review_isolation ON municipality.rule_review USING (
  EXISTS (SELECT 1 FROM municipality.tenant mt
          WHERE mt.id=municipality.rule_review.municipality_tenant_id
            AND mt.organization_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
);

INSERT INTO rural.layer_catalog(code,title,authority,legal_nature,status,metadata) VALUES
  ('CAR','Cadastro Ambiental Rural','SICAR / órgão ambiental competente','environmental_registry','CONFIGURED','{"requires_official_snapshot":true}'::jsonb),
  ('SIGEF','Sistema de Gestão Fundiária','INCRA','land_registry','CONFIGURED','{"requires_official_snapshot":true}'::jsonb),
  ('IBAMA_EMBARGO','Embargos ambientais','IBAMA','environmental_enforcement','CONFIGURED','{"requires_official_snapshot":true}'::jsonb),
  ('PRODES','Monitoramento do desmatamento','INPE','remote_sensing','CONFIGURED','{"requires_official_snapshot":true}'::jsonb)
ON CONFLICT(code) DO UPDATE SET title=excluded.title,authority=excluded.authority,legal_nature=excluded.legal_nature,metadata=excluded.metadata;

UPDATE core.module SET status='V7_70_MILESTONE' WHERE code IN
('imovel360','re-rural','condominio','energia-solar','ai-tec','prefeitura','relatorios');

CREATE INDEX IF NOT EXISTS condo_document_chunk_fts_idx ON condo.document_chunk USING gin(to_tsvector('portuguese',text_content));
CREATE INDEX IF NOT EXISTS ingest_document_text_fts_idx ON ingest.document_text USING gin(to_tsvector('portuguese',text_content));

INSERT INTO core.entitlement_snapshot(organization_id,snapshot,valid_from)
SELECT '0198f001-0000-7000-8000-000000000001'::uuid,
       '{"tier":"local-v7","modules":["imovel360","re-rural","condominio","energia-solar","ai-tec","prefeitura","relatorios"],"quotas":{}}'::jsonb,
       now()
WHERE NOT EXISTS (
  SELECT 1 FROM core.entitlement_snapshot
  WHERE organization_id='0198f001-0000-7000-8000-000000000001'::uuid AND valid_to IS NULL
);
