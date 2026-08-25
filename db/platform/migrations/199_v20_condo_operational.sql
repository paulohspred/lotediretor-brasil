-- v20: Condomínio 360 governance, voting, sanctions, integrations and retrieval ACL.
-- Guardrail: parser/monitor outputs remain candidates; sanctions require explicit human due process.

CREATE TABLE IF NOT EXISTS condo.document_clause(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES condo.document(id) ON DELETE CASCADE,
  clause_code text,
  clause_text text NOT NULL,
  page_from integer CHECK(page_from IS NULL OR page_from >= 1),
  page_to integer CHECK(page_to IS NULL OR page_to >= 1),
  citations jsonb NOT NULL DEFAULT '[]'::jsonb,
  extraction_method text NOT NULL,
  parser_version text NOT NULL,
  confidence numeric CHECK(confidence IS NULL OR (confidence>=0 AND confidence<=1)),
  status text NOT NULL DEFAULT 'CANDIDATE' CHECK(status IN ('CANDIDATE','CONFIRMED','REJECTED')),
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(status <> 'CONFIRMED' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS condo_document_clause_doc_idx ON condo.document_clause(document_id,page_from,id);

ALTER TABLE condo.rule ADD COLUMN IF NOT EXISTS source_clause_id uuid REFERENCES condo.document_clause(id) ON DELETE SET NULL;
ALTER TABLE condo.rule ADD COLUMN IF NOT EXISTS precedence integer;
ALTER TABLE condo.rule ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS condo.rule_relation(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  left_rule_id uuid NOT NULL REFERENCES condo.rule(id) ON DELETE CASCADE,
  right_rule_id uuid NOT NULL REFERENCES condo.rule(id) ON DELETE CASCADE,
  relation text NOT NULL CHECK(relation IN ('AMENDS','SUPERSEDES','EXCEPTS','CONFLICTS_WITH','DEPENDS_ON')),
  effective_from timestamptz,
  effective_to timestamptz,
  status text NOT NULL DEFAULT 'CANDIDATE' CHECK(status IN ('CANDIDATE','CONFIRMED','REJECTED')),
  evidence_clause_ids uuid[] NOT NULL DEFAULT '{}',
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(left_rule_id<>right_rule_id),
  CHECK(status <> 'CONFIRMED' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
  UNIQUE(tenant_id,left_rule_id,right_rule_id,relation)
);

CREATE TABLE IF NOT EXISTS condo.ballot(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  assembly_id uuid NOT NULL REFERENCES condo.assembly(id) ON DELETE CASCADE,
  agenda_item_id uuid NOT NULL REFERENCES condo.agenda_item(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','OPEN','CLOSED','CALCULATED','ENACTED','CANCELLED')),
  eligibility_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  eligibility_sha256 text NOT NULL,
  quorum_rule jsonb NOT NULL,
  opens_at timestamptz,
  closes_at timestamptz,
  calculated_result jsonb NOT NULL DEFAULT '{}'::jsonb,
  enacted_by text,
  enacted_at timestamptz,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(status <> 'ENACTED' OR (enacted_by IS NOT NULL AND enacted_at IS NOT NULL)),
  UNIQUE(agenda_item_id)
);

CREATE TABLE IF NOT EXISTS condo.ballot_vote(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  ballot_id uuid NOT NULL REFERENCES condo.ballot(id) ON DELETE CASCADE,
  voter_subject_hash text NOT NULL,
  choice text NOT NULL CHECK(choice IN ('FOR','AGAINST','ABSTAIN')),
  signature_status text NOT NULL DEFAULT 'PENDING' CHECK(signature_status IN ('PENDING','VERIFIED','REJECTED')),
  signature_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  cast_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(ballot_id,voter_subject_hash)
);

CREATE TABLE IF NOT EXISTS condo.signature_envelope(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  subject_type text NOT NULL CHECK(subject_type IN ('ASSEMBLY','DECISION','SANCTION','DOCUMENT')),
  subject_id uuid NOT NULL,
  provider_code text,
  provider_envelope_id text,
  provider_secret_ref text,
  status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','SENT','PARTIALLY_SIGNED','SIGNED','REJECTED','EXPIRED','CANCELLED')),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  completed_at timestamptz,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS condo.sanction_case(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  unit_id uuid REFERENCES condo.unit(id) ON DELETE SET NULL,
  occurrence_id uuid REFERENCES condo.occurrence(id) ON DELETE SET NULL,
  source_rule_id uuid NOT NULL REFERENCES condo.rule(id),
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','NOTICE_PENDING','DEFENSE_OPEN','UNDER_HUMAN_REVIEW','READY_FOR_MANUAL_ISSUANCE','ISSUED','REJECTED','CANCELLED')),
  proposed_kind text NOT NULL CHECK(proposed_kind IN ('WARNING','FINE','OTHER')),
  proposed_amount_cents bigint CHECK(proposed_amount_cents IS NULL OR proposed_amount_cents>=0),
  evidence_ids uuid[] NOT NULL DEFAULT '{}',
  notice_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  defense_due_at timestamptz,
  human_decision text CHECK(human_decision IS NULL OR human_decision IN ('APPROVE','REJECT')),
  human_decision_by text,
  human_decision_reason text,
  human_decision_at timestamptz,
  issued_by text,
  issued_at timestamptz,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(status NOT IN ('READY_FOR_MANUAL_ISSUANCE','ISSUED','REJECTED') OR (human_decision IS NOT NULL AND human_decision_by IS NOT NULL AND human_decision_reason IS NOT NULL AND human_decision_at IS NOT NULL)),
  CHECK(status <> 'ISSUED' OR (human_decision='APPROVE' AND issued_by IS NOT NULL AND issued_at IS NOT NULL)),
  CHECK(status <> 'REJECTED' OR human_decision='REJECT')
);
CREATE INDEX IF NOT EXISTS condo_sanction_condo_idx ON condo.sanction_case(condominium_id,status,created_at DESC);

CREATE TABLE IF NOT EXISTS condo.defense(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  sanction_case_id uuid NOT NULL REFERENCES condo.sanction_case(id) ON DELETE CASCADE,
  submitted_by text,
  defense_text text NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'SUBMITTED' CHECK(status IN ('SUBMITTED','UNDER_REVIEW','RESOLVED','WITHDRAWN')),
  resolution text,
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(status <> 'RESOLVED' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL AND resolution IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS condo.charge(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  unit_id uuid REFERENCES condo.unit(id) ON DELETE SET NULL,
  sanction_case_id uuid REFERENCES condo.sanction_case(id) ON DELETE SET NULL,
  amount_cents bigint NOT NULL CHECK(amount_cents>=0),
  due_date date,
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','READY_FOR_BILLING','BILLED','PAID','CANCELLED')),
  external_reference text,
  billing_provider text,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS condo.communication_endpoint(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  provider_code text NOT NULL,
  channel text NOT NULL CHECK(channel IN ('EMAIL','SMS','WHATSAPP','PUSH','ADMIN_API','OTHER')),
  endpoint_ref text,
  secret_ref text,
  status text NOT NULL DEFAULT 'CONFIGURED' CHECK(status IN ('CONFIGURED','DISABLED')),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,condominium_id,provider_code,channel)
);

CREATE TABLE IF NOT EXISTS condo.communication_log(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  endpoint_id uuid REFERENCES condo.communication_endpoint(id) ON DELETE SET NULL,
  subject_type text,
  subject_id uuid,
  recipient_ref_hash text,
  template_code text,
  status text NOT NULL DEFAULT 'QUEUED' CHECK(status IN ('QUEUED','SENT','DELIVERED','FAILED','CANCELLED')),
  provider_message_id text,
  payload_sha256 text,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS condo.legal_monitor(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  source_code text NOT NULL,
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','PAUSED','DISABLED')),
  configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_snapshot_id uuid REFERENCES source.snapshot(id),
  last_checked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,condominium_id,source_code)
);

CREATE TABLE IF NOT EXISTS condo.legal_monitor_event(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  monitor_id uuid NOT NULL REFERENCES condo.legal_monitor(id) ON DELETE CASCADE,
  before_snapshot_id uuid REFERENCES source.snapshot(id),
  after_snapshot_id uuid REFERENCES source.snapshot(id),
  status text NOT NULL DEFAULT 'CANDIDATE_REVIEW' CHECK(status IN ('CANDIDATE_REVIEW','CONFIRMED','REJECTED')),
  change_summary jsonb NOT NULL,
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(status='CANDIDATE_REVIEW' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS condo.integration_link(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  target_type text NOT NULL CHECK(target_type IN ('PROPERTY','AITEC_PROJECT')),
  target_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','DISABLED')),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,condominium_id,target_type,target_id)
);

CREATE TABLE IF NOT EXISTS condo.retrieval_acl(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES condo.document(id) ON DELETE CASCADE,
  subject_type text NOT NULL CHECK(subject_type IN ('ROLE','USER','EXTERNAL_MODE')),
  subject_ref text NOT NULL,
  permission text NOT NULL DEFAULT 'READ' CHECK(permission IN ('READ')),
  valid_from timestamptz,
  valid_to timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,document_id,subject_type,subject_ref)
);
CREATE INDEX IF NOT EXISTS condo_retrieval_acl_lookup_idx ON condo.retrieval_acl(tenant_id,condominium_id,subject_type,subject_ref,document_id);

DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT * FROM (VALUES
    ('condo','document_clause'),('condo','rule_relation'),('condo','ballot'),('condo','ballot_vote'),('condo','signature_envelope'),
    ('condo','sanction_case'),('condo','defense'),('condo','charge'),('condo','communication_endpoint'),('condo','communication_log'),
    ('condo','legal_monitor'),('condo','legal_monitor_event'),('condo','integration_link'),('condo','retrieval_acl')
  ) AS x(schemaname,tablename)
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I.%I',r.schemaname,r.tablename);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I.%I USING (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',r.schemaname,r.tablename);
  END LOOP;
END $$;

GRANT SELECT,INSERT,UPDATE,DELETE ON
  condo.document_clause,condo.rule_relation,condo.ballot,condo.ballot_vote,condo.signature_envelope,
  condo.sanction_case,condo.defense,condo.charge,condo.communication_endpoint,condo.communication_log,
  condo.legal_monitor,condo.legal_monitor_event,condo.integration_link,condo.retrieval_acl
TO lotediretor_app,lotediretor_worker;

UPDATE core.module SET status='V20_OPERATIONAL_IMPLEMENTATION' WHERE code='condominio';
