-- v20: Prefeitura/B2G operational governance, publication and institutional ACL.
-- Official upstream systems remain external gates; this migration adds the auditable control plane.

CREATE TABLE IF NOT EXISTS municipality.department(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  code text NOT NULL,
  name text NOT NULL,
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','INACTIVE')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(municipality_tenant_id,code)
);

CREATE TABLE IF NOT EXISTS municipality.member_role(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  department_id uuid REFERENCES municipality.department(id) ON DELETE SET NULL,
  subject_id text NOT NULL,
  role text NOT NULL CHECK(role IN ('MUNICIPAL_ADMIN','DATA_STEWARD','LEGAL_REVIEWER','GIS_EDITOR','TAX_EDITOR','LICENSING_AGENT','AUDITOR','VIEWER','AI_USER')),
  permission_overrides text[] NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','SUSPENDED','REVOKED')),
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  UNIQUE(municipality_tenant_id,subject_id,role,department_id)
);
CREATE INDEX IF NOT EXISTS municipality_member_subject_idx ON municipality.member_role(municipality_tenant_id,subject_id,status);

CREATE TABLE IF NOT EXISTS municipality.dataset(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  dataset_code text NOT NULL,
  title text NOT NULL,
  kind text NOT NULL CHECK(kind IN ('LEGAL','GIS','CTM','CIB_SINTER','PGV','IPTU','ITBI','PARCELAMENTO','ALVARA','HABITE_SE','LICENCIAMENTO','OPEN_DATA','OTHER')),
  visibility text NOT NULL DEFAULT 'INTERNAL' CHECK(visibility IN ('OPEN','RESTRICTED','INTERNAL')),
  source_id uuid REFERENCES source.registry(id),
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','ACTIVE','INACTIVE','OFFBOARDING')),
  publication_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(municipality_tenant_id,dataset_code)
);

CREATE TABLE IF NOT EXISTS municipality.dataset_acl(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  dataset_id uuid NOT NULL REFERENCES municipality.dataset(id) ON DELETE CASCADE,
  principal_kind text NOT NULL CHECK(principal_kind IN ('ROLE','SUBJECT')),
  principal_value text NOT NULL,
  permissions text[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(dataset_id,principal_kind,principal_value)
);

CREATE TABLE IF NOT EXISTS municipality.dataset_snapshot(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  dataset_id uuid NOT NULL REFERENCES municipality.dataset(id) ON DELETE CASCADE,
  source_snapshot_id uuid NOT NULL REFERENCES source.snapshot(id),
  base_date date NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','VALIDATED','PUBLISHED','SUPERSEDED','REVOKED')),
  validation jsonb NOT NULL DEFAULT '{}'::jsonb,
  impact_geom geometry(Geometry,4326),
  checksum_manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  validated_by text,
  validated_at timestamptz,
  published_by text,
  published_at timestamptz,
  superseded_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(dataset_id,source_snapshot_id),
  CHECK(status NOT IN ('VALIDATED','PUBLISHED','SUPERSEDED') OR (validated_by IS NOT NULL AND validated_at IS NOT NULL)),
  CHECK(status NOT IN ('PUBLISHED','SUPERSEDED') OR (published_by IS NOT NULL AND published_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS municipality_dataset_one_published_uq ON municipality.dataset_snapshot(dataset_id) WHERE status='PUBLISHED';
CREATE INDEX IF NOT EXISTS municipality_dataset_snapshot_geom_gix ON municipality.dataset_snapshot USING gist(impact_geom);

CREATE TABLE IF NOT EXISTS municipality.publication_event_v20(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  dataset_id uuid NOT NULL REFERENCES municipality.dataset(id) ON DELETE CASCADE,
  action text NOT NULL CHECK(action IN ('PUBLISH','ROLLBACK','REVOKE')),
  previous_dataset_snapshot_id uuid REFERENCES municipality.dataset_snapshot(id),
  new_dataset_snapshot_id uuid REFERENCES municipality.dataset_snapshot(id),
  actor text NOT NULL,
  reason text NOT NULL,
  affected_property_count integer NOT NULL DEFAULT 0 CHECK(affected_property_count>=0),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS municipality.recalculation_job(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  publication_event_id uuid NOT NULL REFERENCES municipality.publication_event_v20(id) ON DELETE CASCADE,
  property_id uuid NOT NULL REFERENCES property360.property(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
  analysis_run_id uuid REFERENCES analysis.run(id) ON DELETE SET NULL,
  attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(publication_event_id,property_id)
);
CREATE INDEX IF NOT EXISTS municipality_recalc_pending_idx ON municipality.recalculation_job(municipality_tenant_id,status,created_at);

CREATE TABLE IF NOT EXISTS municipality.pgv_value(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  cadastral_code text,
  zone_code text,
  reference_year integer NOT NULL,
  land_value_cents_m2 bigint CHECK(land_value_cents_m2 IS NULL OR land_value_cents_m2>=0),
  building_value_cents_m2 bigint CHECK(building_value_cents_m2 IS NULL OR building_value_cents_m2>=0),
  source_snapshot_id uuid NOT NULL REFERENCES source.snapshot(id),
  valid_from date NOT NULL,
  valid_to date,
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(cadastral_code IS NOT NULL OR zone_code IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS municipality.itbi_record(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  protocol text NOT NULL,
  cadastral_code text,
  transaction_date date,
  declared_value_cents bigint CHECK(declared_value_cents IS NULL OR declared_value_cents>=0),
  assessed_value_cents bigint CHECK(assessed_value_cents IS NULL OR assessed_value_cents>=0),
  tax_value_cents bigint CHECK(tax_value_cents IS NULL OR tax_value_cents>=0),
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(municipality_tenant_id,protocol)
);

CREATE TABLE IF NOT EXISTS municipality.licensing_case(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  case_type text NOT NULL CHECK(case_type IN ('PARCELAMENTO','ALVARA','HABITE_SE','LICENCIAMENTO')),
  protocol text NOT NULL,
  cadastral_code text,
  property_id uuid REFERENCES property360.property(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'SUBMITTED' CHECK(status IN ('SUBMITTED','UNDER_REVIEW','MORE_INFO','APPROVED','REJECTED','CANCELLED')),
  applicant_ref text,
  evidence_ids uuid[] NOT NULL DEFAULT '{}',
  source_snapshot_ids uuid[] NOT NULL DEFAULT '{}',
  decision_reason text,
  decided_by text,
  decided_at timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(municipality_tenant_id,case_type,protocol),
  CHECK(status NOT IN ('APPROVED','REJECTED') OR (decided_by IS NOT NULL AND decided_at IS NOT NULL AND decision_reason IS NOT NULL AND cardinality(evidence_ids)>0))
);

CREATE TABLE IF NOT EXISTS municipality.audit_event_v20(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  actor text NOT NULL,
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_id text,
  before_state jsonb,
  after_state jsonb,
  evidence_ids uuid[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS municipality_audit_v20_idx ON municipality.audit_event_v20(municipality_tenant_id,created_at DESC);

CREATE TABLE IF NOT EXISTS municipality.export_job(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'READY' CHECK(status IN ('READY','EXPIRED','REVOKED')),
  requested_by text NOT NULL,
  manifest jsonb NOT NULL,
  checksum_sha256 text NOT NULL,
  object_key text,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz
);

CREATE TABLE IF NOT EXISTS municipality.offboarding_case(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  export_job_id uuid NOT NULL REFERENCES municipality.export_job(id),
  status text NOT NULL DEFAULT 'REQUESTED' CHECK(status IN ('REQUESTED','APPROVED','COMPLETED','CANCELLED')),
  requested_by text NOT NULL,
  approved_by text,
  completed_at timestamptz,
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT * FROM (VALUES
    ('department'),('member_role'),('dataset'),('dataset_acl'),('dataset_snapshot'),('publication_event_v20'),('recalculation_job'),
    ('pgv_value'),('itbi_record'),('licensing_case'),('audit_event_v20'),('export_job'),('offboarding_case')
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

GRANT SELECT,INSERT,UPDATE,DELETE ON municipality.department,municipality.member_role,municipality.dataset,municipality.dataset_acl,municipality.dataset_snapshot,municipality.recalculation_job,municipality.pgv_value,municipality.itbi_record,municipality.licensing_case,municipality.export_job,municipality.offboarding_case TO lotediretor_app,lotediretor_worker;
GRANT SELECT,INSERT ON municipality.publication_event_v20,municipality.audit_event_v20 TO lotediretor_app,lotediretor_worker;

UPDATE core.module SET status='V20_OPERATIONAL_IMPLEMENTATION' WHERE code='prefeitura';
