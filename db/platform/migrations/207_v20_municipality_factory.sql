-- v20 Municipality Factory: reusable source contracts, connector lifecycle, QA, goldens and national coverage.
-- Discovery and ingestion are operational states; neither one implies legal/municipal homologation.

CREATE TABLE IF NOT EXISTS source.connector_contract(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  code text NOT NULL,
  version integer NOT NULL DEFAULT 1 CHECK(version>0),
  adapter text NOT NULL CHECK(adapter IN ('WFS','WMS','ARCGIS','CKAN','HTML','PDF','ZIP')),
  media_class text NOT NULL CHECK(media_class IN ('GIS','DOCUMENT','MIXED')),
  schema_contract jsonb NOT NULL DEFAULT '{}'::jsonb,
  discovery_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
  ingest_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
  qa_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','RETIRED')),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(code,version)
);

CREATE TABLE IF NOT EXISTS municipality.factory_source(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  municipality_ibge text NOT NULL,
  dataset_code text NOT NULL,
  source_id uuid NOT NULL REFERENCES source.registry(id),
  contract_id uuid REFERENCES source.connector_contract(id),
  adapter text NOT NULL CHECK(adapter IN ('WFS','WMS','ARCGIS','CKAN','HTML','PDF','ZIP')),
  endpoint_url text NOT NULL,
  pinned_config jsonb NOT NULL DEFAULT '{}'::jsonb,
  connector_status text NOT NULL DEFAULT 'CANDIDATE' CHECK(connector_status IN ('CANDIDATE','DISCOVERED','ACTIVE','PAUSED','UNAVAILABLE','FAILED')),
  homologation_status text NOT NULL DEFAULT 'UNREVIEWED' CHECK(homologation_status IN ('UNREVIEWED','CANDIDATE','CONFIRMED','REJECTED','UNAVAILABLE')),
  license_status text NOT NULL DEFAULT 'UNVERIFIED' CHECK(license_status IN ('UNVERIFIED','VERIFIED','RESTRICTED','BLOCKED')),
  license_url text,
  license_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_discovered_at timestamptz,
  last_ingested_at timestamptz,
  last_success_at timestamptz,
  next_check_at timestamptz,
  reviewed_by text,
  reviewed_at timestamptz,
  review_reason text,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(municipality_tenant_id,dataset_code,source_id)
);
CREATE INDEX IF NOT EXISTS municipality_factory_source_status_idx ON municipality.factory_source(municipality_tenant_id,connector_status,homologation_status);

CREATE TABLE IF NOT EXISTS municipality.factory_discovery(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  factory_source_id uuid NOT NULL REFERENCES municipality.factory_source(id) ON DELETE CASCADE,
  adapter text NOT NULL,
  requested_url text NOT NULL,
  resolved_url text,
  http_status integer,
  content_type text,
  capability_sha256 text,
  capability_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL CHECK(status IN ('PASS','WARN','FAIL','BLOCKED')),
  error_code text,
  error_detail text,
  discovered_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS municipality_factory_discovery_idx ON municipality.factory_discovery(factory_source_id,discovered_at DESC);

CREATE TABLE IF NOT EXISTS municipality.factory_connector_run(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  factory_source_id uuid NOT NULL REFERENCES municipality.factory_source(id) ON DELETE CASCADE,
  run_kind text NOT NULL CHECK(run_kind IN ('DISCOVERY','INGEST','QA','MONITOR')),
  status text NOT NULL DEFAULT 'RUNNING' CHECK(status IN ('RUNNING','SUCCEEDED','FAILED','BLOCKED')),
  request_fingerprint text NOT NULL,
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  object_key text,
  sha256 text,
  byte_size bigint CHECK(byte_size IS NULL OR byte_size>=0),
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_code text,
  error_detail text,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  UNIQUE(factory_source_id,run_kind,request_fingerprint)
);
CREATE INDEX IF NOT EXISTS municipality_factory_run_idx ON municipality.factory_connector_run(factory_source_id,started_at DESC);

CREATE TABLE IF NOT EXISTS municipality.factory_qa_result(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  factory_source_id uuid NOT NULL REFERENCES municipality.factory_source(id) ON DELETE CASCADE,
  source_snapshot_id uuid NOT NULL REFERENCES source.snapshot(id),
  qa_kind text NOT NULL CHECK(qa_kind IN ('GIS','LEGAL','STRUCTURE','LICENSE','TEMPORAL')),
  status text NOT NULL CHECK(status IN ('PASS','WARN','FAIL')),
  score numeric(6,5) CHECK(score IS NULL OR (score>=0 AND score<=1)),
  checks jsonb NOT NULL DEFAULT '[]'::jsonb,
  reviewer text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(source_snapshot_id,qa_kind)
);

CREATE TABLE IF NOT EXISTS municipality.factory_rule_candidate(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  factory_source_id uuid NOT NULL REFERENCES municipality.factory_source(id) ON DELETE CASCADE,
  source_snapshot_id uuid NOT NULL REFERENCES source.snapshot(id),
  municipality_ibge text NOT NULL,
  document_version_id uuid REFERENCES legal.document_version(id),
  candidate_key text NOT NULL,
  payload jsonb NOT NULL,
  evidence_locator text NOT NULL,
  status text NOT NULL DEFAULT 'CANDIDATE' CHECK(status IN ('CANDIDATE','CONFIRMED','REJECTED')),
  generated_by text NOT NULL,
  reviewed_by text,
  reviewed_at timestamptz,
  review_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(source_snapshot_id,candidate_key)
);

CREATE TABLE IF NOT EXISTS municipality.factory_golden_case(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  municipality_ibge text NOT NULL,
  dataset_code text NOT NULL,
  case_key text NOT NULL,
  fixture jsonb NOT NULL,
  expected jsonb NOT NULL,
  professional_review_status text NOT NULL DEFAULT 'PENDING' CHECK(professional_review_status IN ('PENDING','APPROVED','REJECTED')),
  reviewed_by text,
  reviewed_at timestamptz,
  review_notes text,
  active boolean NOT NULL DEFAULT true,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(municipality_tenant_id,dataset_code,case_key)
);

CREATE TABLE IF NOT EXISTS municipality.factory_golden_run(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  factory_source_id uuid NOT NULL REFERENCES municipality.factory_source(id) ON DELETE CASCADE,
  source_snapshot_id uuid NOT NULL REFERENCES source.snapshot(id),
  status text NOT NULL CHECK(status IN ('PASS','FAIL','BLOCKED')),
  total_cases integer NOT NULL CHECK(total_cases>=0),
  passed_cases integer NOT NULL CHECK(passed_cases>=0),
  results jsonb NOT NULL DEFAULT '[]'::jsonb,
  runner_version text NOT NULL,
  run_at timestamptz NOT NULL DEFAULT now(),
  CHECK(passed_cases<=total_cases)
);
CREATE INDEX IF NOT EXISTS municipality_factory_golden_run_idx ON municipality.factory_golden_run(factory_source_id,run_at DESC);

CREATE TABLE IF NOT EXISTS municipality.factory_monitor_event(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  factory_source_id uuid NOT NULL REFERENCES municipality.factory_source(id) ON DELETE CASCADE,
  previous_sha256 text,
  observed_sha256 text,
  change_kind text NOT NULL CHECK(change_kind IN ('UNCHANGED','CONTENT_CHANGED','SCHEMA_CHANGED','ENDPOINT_DOWN','ENDPOINT_RECOVERED','LICENSE_CHANGED')),
  severity text NOT NULL DEFAULT 'INFO' CHECK(severity IN ('INFO','WARN','BLOCKING')),
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  observed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS municipality_factory_monitor_idx ON municipality.factory_monitor_event(factory_source_id,observed_at DESC);

CREATE TABLE IF NOT EXISTS municipality.factory_coverage_snapshot(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  generated_at timestamptz NOT NULL DEFAULT now(),
  municipality_count integer NOT NULL DEFAULT 0,
  source_count integer NOT NULL DEFAULT 0,
  active_connector_count integer NOT NULL DEFAULT 0,
  confirmed_source_count integer NOT NULL DEFAULT 0,
  unavailable_source_count integer NOT NULL DEFAULT 0,
  latest_qa_pass_count integer NOT NULL DEFAULT 0,
  latest_golden_pass_count integer NOT NULL DEFAULT 0,
  by_adapter jsonb NOT NULL DEFAULT '{}'::jsonb,
  by_uf jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT * FROM (VALUES
    ('factory_source'),('factory_discovery'),('factory_connector_run'),('factory_qa_result'),
    ('factory_rule_candidate'),('factory_golden_case'),('factory_golden_run'),('factory_monitor_event')
  ) AS x(tablename)
  LOOP
    EXECUTE format('ALTER TABLE municipality.%I ENABLE ROW LEVEL SECURITY',r.tablename);
    EXECUTE format('ALTER TABLE municipality.%I FORCE ROW LEVEL SECURITY',r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON municipality.%I',r.tablename);
    EXECUTE format($p$CREATE POLICY tenant_isolation ON municipality.%I USING (
      EXISTS(SELECT 1 FROM municipality.tenant mt WHERE mt.id=municipality.%I.municipality_tenant_id AND mt.organization_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
    ) WITH CHECK (
      EXISTS(SELECT 1 FROM municipality.tenant mt WHERE mt.id=municipality.%I.municipality_tenant_id AND mt.organization_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
    )$p$,r.tablename,r.tablename,r.tablename);
  END LOOP;
END $$;

GRANT SELECT ON source.connector_contract TO lotediretor_app,lotediretor_worker;
GRANT SELECT,INSERT,UPDATE ON source.connector_contract TO lotediretor_worker;
GRANT SELECT,INSERT,UPDATE,DELETE ON municipality.factory_source,municipality.factory_discovery,municipality.factory_connector_run,municipality.factory_qa_result,municipality.factory_rule_candidate,municipality.factory_golden_case,municipality.factory_golden_run,municipality.factory_monitor_event TO lotediretor_app,lotediretor_worker;
GRANT SELECT ON municipality.factory_coverage_snapshot TO lotediretor_app,lotediretor_worker;
GRANT SELECT,INSERT ON municipality.factory_coverage_snapshot TO lotediretor_worker;
