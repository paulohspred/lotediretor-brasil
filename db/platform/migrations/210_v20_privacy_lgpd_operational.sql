-- v20 privacy/LGPD operational workflow.
-- Destructive operations are deliberately narrow: provenance, legal evidence and audit records are never purged by this migration.

CREATE SCHEMA IF NOT EXISTS privacy;

ALTER TABLE iam.user_profile
  ADD COLUMN IF NOT EXISTS privacy_status text NOT NULL DEFAULT 'ACTIVE',
  ADD COLUMN IF NOT EXISTS anonymized_at timestamptz,
  ADD COLUMN IF NOT EXISTS privacy_note text;

CREATE TABLE IF NOT EXISTS privacy.subject_request(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES iam.organization(id),
  subject_user_id uuid NOT NULL REFERENCES iam.user_profile(id),
  request_type text NOT NULL CHECK(request_type IN ('ACCESS','PORTABILITY','RECTIFICATION','RESTRICTION','ERASURE')),
  status text NOT NULL DEFAULT 'REQUESTED' CHECK(status IN ('REQUESTED','IDENTITY_VERIFIED','APPROVED','REJECTED','EXECUTING','COMPLETED')),
  request_reason text,
  requested_by uuid,
  reviewed_by uuid,
  verified_at timestamptz,
  decided_at timestamptz,
  completed_at timestamptz,
  rejection_reason text,
  result_manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS subject_request_tenant_subject_idx ON privacy.subject_request(tenant_id,subject_user_id,created_at DESC);

CREATE TABLE IF NOT EXISTS privacy.legal_hold(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES iam.organization(id),
  subject_user_id uuid REFERENCES iam.user_profile(id),
  data_category text NOT NULL DEFAULT 'ALL',
  reason text NOT NULL,
  legal_basis text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  starts_at timestamptz NOT NULL DEFAULT now(),
  ends_at timestamptz,
  created_by uuid,
  released_by uuid,
  released_at timestamptz,
  release_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(ends_at IS NULL OR ends_at>starts_at)
);
CREATE INDEX IF NOT EXISTS legal_hold_active_idx ON privacy.legal_hold(tenant_id,subject_user_id,active) WHERE active;

CREATE TABLE IF NOT EXISTS privacy.retention_policy(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES iam.organization(id),
  data_category text NOT NULL,
  retention_days integer NOT NULL CHECK(retention_days>=0),
  expiry_action text NOT NULL CHECK(expiry_action IN ('RETAIN','ANONYMIZE','DELETE')),
  legal_basis text NOT NULL,
  automatic_execution boolean NOT NULL DEFAULT false,
  protected_class boolean NOT NULL DEFAULT false,
  owner text NOT NULL,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,data_category),
  CHECK(NOT (protected_class AND expiry_action='DELETE'))
);

CREATE TABLE IF NOT EXISTS privacy.operation_event(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES iam.organization(id),
  subject_user_id uuid,
  request_id uuid REFERENCES privacy.subject_request(id),
  action text NOT NULL,
  actor_id uuid,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS privacy_operation_event_idx ON privacy.operation_event(tenant_id,subject_user_id,created_at DESC);

CREATE OR REPLACE FUNCTION privacy.guard_subject_request_terminal() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at=now();
  IF OLD.status IN ('COMPLETED','REJECTED') AND NEW IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION 'privacy_terminal_request_is_immutable';
  END IF;
  IF NEW.status='IDENTITY_VERIFIED' AND OLD.status='REQUESTED' AND NEW.verified_at IS NULL THEN
    RAISE EXCEPTION 'privacy_identity_verification_requires_timestamp';
  END IF;
  IF NEW.status IN ('APPROVED','REJECTED') AND OLD.status IS DISTINCT FROM NEW.status AND NEW.decided_at IS NULL THEN
    RAISE EXCEPTION 'privacy_decision_requires_timestamp';
  END IF;
  IF NEW.status='COMPLETED' AND OLD.status IS DISTINCT FROM 'COMPLETED' AND NEW.completed_at IS NULL THEN
    RAISE EXCEPTION 'privacy_completion_requires_timestamp';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS subject_request_terminal_guard ON privacy.subject_request;
CREATE TRIGGER subject_request_terminal_guard BEFORE UPDATE ON privacy.subject_request FOR EACH ROW EXECUTE FUNCTION privacy.guard_subject_request_terminal();

CREATE OR REPLACE FUNCTION privacy.guard_legal_hold_release() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.active=false AND NEW IS DISTINCT FROM OLD THEN RAISE EXCEPTION 'released_legal_hold_is_immutable'; END IF;
  IF OLD.active=true AND NEW.active=false AND (NEW.released_at IS NULL OR NEW.released_by IS NULL OR nullif(trim(NEW.release_reason),'') IS NULL) THEN
    RAISE EXCEPTION 'legal_hold_release_requires_actor_timestamp_reason';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS legal_hold_release_guard ON privacy.legal_hold;
CREATE TRIGGER legal_hold_release_guard BEFORE UPDATE ON privacy.legal_hold FOR EACH ROW EXECUTE FUNCTION privacy.guard_legal_hold_release();

CREATE OR REPLACE FUNCTION privacy.has_active_hold(p_tenant uuid,p_subject uuid,p_category text DEFAULT 'IDENTITY') RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog,privacy AS $$
  SELECT EXISTS(
    SELECT 1 FROM privacy.legal_hold h
    WHERE h.tenant_id=p_tenant
      AND h.active
      AND (h.ends_at IS NULL OR h.ends_at>now())
      AND (h.subject_user_id IS NULL OR h.subject_user_id=p_subject)
      AND (h.data_category='ALL' OR h.data_category=p_category)
  );
$$;

ALTER TABLE privacy.subject_request ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy.subject_request FORCE ROW LEVEL SECURITY;
ALTER TABLE privacy.legal_hold ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy.legal_hold FORCE ROW LEVEL SECURITY;
ALTER TABLE privacy.retention_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy.retention_policy FORCE ROW LEVEL SECURITY;
ALTER TABLE privacy.operation_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy.operation_event FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON privacy.subject_request;
CREATE POLICY tenant_isolation ON privacy.subject_request FOR ALL TO lotediretor_app
USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
DROP POLICY IF EXISTS tenant_isolation ON privacy.legal_hold;
CREATE POLICY tenant_isolation ON privacy.legal_hold FOR ALL TO lotediretor_app
USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
DROP POLICY IF EXISTS tenant_isolation ON privacy.retention_policy;
CREATE POLICY tenant_isolation ON privacy.retention_policy FOR ALL TO lotediretor_app
USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
DROP POLICY IF EXISTS tenant_isolation ON privacy.operation_event;
CREATE POLICY tenant_isolation ON privacy.operation_event FOR ALL TO lotediretor_app
USING(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK(tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);

GRANT USAGE ON SCHEMA privacy TO lotediretor_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA privacy TO lotediretor_app;
GRANT EXECUTE ON FUNCTION privacy.has_active_hold(uuid,uuid,text) TO lotediretor_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA privacy GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO lotediretor_app;

-- Conservative defaults. Tenant administrators may tune retention only after documenting legal basis.
INSERT INTO privacy.retention_policy(tenant_id,data_category,retention_days,expiry_action,legal_basis,automatic_execution,protected_class,owner,notes)
SELECT o.id,'AUDIT_TRAIL',1825,'RETAIN','legitimate_interest_and_compliance',false,true,'security','Append-only operational evidence; never deleted automatically.' FROM iam.organization o
ON CONFLICT(tenant_id,data_category) DO NOTHING;
INSERT INTO privacy.retention_policy(tenant_id,data_category,retention_days,expiry_action,legal_basis,automatic_execution,protected_class,owner,notes)
SELECT o.id,'LEGAL_EVIDENCE',3650,'RETAIN','legal_claims_and_regulatory_evidence',false,true,'legal','Legal/provenance evidence requires explicit reviewed disposition.' FROM iam.organization o
ON CONFLICT(tenant_id,data_category) DO NOTHING;
INSERT INTO privacy.retention_policy(tenant_id,data_category,retention_days,expiry_action,legal_basis,automatic_execution,protected_class,owner,notes)
SELECT o.id,'IDENTITY_PROFILE',30,'ANONYMIZE','data_subject_erasure_or_end_of_relationship',false,false,'privacy','Execution is request-driven and blocked by active legal holds.' FROM iam.organization o
ON CONFLICT(tenant_id,data_category) DO NOTHING;

COMMENT ON TABLE privacy.subject_request IS 'LGPD/data-subject workflow. ERASURE is tenant-scoped and must preserve protected legal/audit/provenance classes.';
COMMENT ON TABLE privacy.legal_hold IS 'Explicit legal/compliance hold; active holds block identity erasure for matching tenant/subject/category.';
COMMENT ON TABLE privacy.retention_policy IS 'Retention policy registry. Automatic destructive execution is disabled by default.';
