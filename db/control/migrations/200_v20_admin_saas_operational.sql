-- v20 Admin SaaS: tenant-scoped commercial operations, privileged support, analytics and DR evidence.
-- External fiscal/payment providers remain execution gates; this migration stores auditable orchestration state.

ALTER TABLE admin.audit_event ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES tenant.tenant(id);
ALTER TABLE admin.audit_event ADD COLUMN IF NOT EXISTS request_id text;
ALTER TABLE admin.audit_event ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE billing.ledger_entry ADD COLUMN IF NOT EXISTS idempotency_key text;
ALTER TABLE billing.ledger_entry ADD COLUMN IF NOT EXISTS external_reference text;
ALTER TABLE billing.ledger_entry ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
CREATE UNIQUE INDEX IF NOT EXISTS billing_ledger_idempotency_uq ON billing.ledger_entry(tenant_id,idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS admin.idempotency_record(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  scope text NOT NULL,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','COMPLETED')),
  response_data jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  UNIQUE(scope,idempotency_key)
);

CREATE TABLE IF NOT EXISTS catalog.service_contract(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  contract_code text NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','ACTIVE','SUSPENDED','TERMINATED','EXPIRED')),
  starts_at timestamptz,
  ends_at timestamptz,
  terms_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  signed_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text NOT NULL,
  activated_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,contract_code)
);

CREATE TABLE IF NOT EXISTS catalog.add_on_version(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  code text NOT NULL,
  version integer NOT NULL CHECK(version>0),
  name text NOT NULL,
  currency char(3) NOT NULL DEFAULT 'BRL',
  monthly_cents bigint CHECK(monthly_cents IS NULL OR monthly_cents>=0),
  entitlements jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','ACTIVE','INACTIVE')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(code,version)
);

CREATE TABLE IF NOT EXISTS catalog.coupon(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  code text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','INACTIVE','EXPIRED')),
  kind text NOT NULL CHECK(kind IN ('PERCENT','FIXED')),
  value numeric(18,4) NOT NULL CHECK(value>=0),
  currency char(3),
  max_redemptions integer CHECK(max_redemptions IS NULL OR max_redemptions>0),
  redeemed_count integer NOT NULL DEFAULT 0 CHECK(redeemed_count>=0),
  valid_from timestamptz,
  valid_to timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS billing.subscription_add_on(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  subscription_id uuid NOT NULL REFERENCES billing.subscription(id) ON DELETE CASCADE,
  add_on_version_id uuid NOT NULL REFERENCES catalog.add_on_version(id),
  quantity integer NOT NULL DEFAULT 1 CHECK(quantity>0),
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','CANCELLED')),
  effective_from timestamptz NOT NULL DEFAULT now(),
  effective_to timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(subscription_id,add_on_version_id,effective_from)
);

CREATE TABLE IF NOT EXISTS billing.invoice(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  subscription_id uuid REFERENCES billing.subscription(id) ON DELETE SET NULL,
  contract_id uuid REFERENCES catalog.service_contract(id) ON DELETE SET NULL,
  coupon_id uuid REFERENCES catalog.coupon(id) ON DELETE SET NULL,
  invoice_number text NOT NULL,
  currency char(3) NOT NULL DEFAULT 'BRL',
  subtotal_cents bigint NOT NULL CHECK(subtotal_cents>=0),
  discount_cents bigint NOT NULL DEFAULT 0 CHECK(discount_cents>=0),
  total_cents bigint NOT NULL CHECK(total_cents>=0),
  paid_cents bigint NOT NULL DEFAULT 0 CHECK(paid_cents>=0),
  status text NOT NULL DEFAULT 'OPEN' CHECK(status IN ('DRAFT','OPEN','PAID','PAST_DUE','VOID','UNCOLLECTIBLE')),
  due_at timestamptz,
  period_start timestamptz,
  period_end timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,invoice_number),
  CHECK(total_cents=greatest(0,subtotal_cents-discount_cents)),
  CHECK(paid_cents<=total_cents)
);

CREATE TABLE IF NOT EXISTS billing.invoice_line(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  invoice_id uuid NOT NULL REFERENCES billing.invoice(id) ON DELETE CASCADE,
  line_type text NOT NULL CHECK(line_type IN ('PLAN','ADD_ON','USAGE','ADJUSTMENT','TAX','OTHER')),
  description text NOT NULL,
  quantity numeric(18,4) NOT NULL DEFAULT 1 CHECK(quantity>=0),
  unit_cents bigint NOT NULL,
  amount_cents bigint NOT NULL,
  reference_type text,
  reference_id uuid,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS billing.dunning_case(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  invoice_id uuid NOT NULL REFERENCES billing.invoice(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','RETRY_SCHEDULED','PAID','EXHAUSTED','CANCELLED')),
  attempt integer NOT NULL DEFAULT 0 CHECK(attempt>=0),
  next_attempt_at timestamptz,
  last_error text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(invoice_id)
);

CREATE TABLE IF NOT EXISTS billing.adjustment(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  payment_id uuid REFERENCES billing.payment(id) ON DELETE SET NULL,
  invoice_id uuid REFERENCES billing.invoice(id) ON DELETE SET NULL,
  kind text NOT NULL CHECK(kind IN ('REFUND','CHARGEBACK','CREDIT','DEBIT')),
  amount_cents bigint NOT NULL CHECK(amount_cents>0),
  currency char(3) NOT NULL DEFAULT 'BRL',
  provider text,
  provider_reference text,
  reason text NOT NULL,
  idempotency_key text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,idempotency_key)
);

CREATE TABLE IF NOT EXISTS billing.reconciliation_run(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  period_start timestamptz NOT NULL,
  period_end timestamptz NOT NULL,
  status text NOT NULL CHECK(status IN ('BALANCED','DIFFERENCE')),
  payment_net_cents bigint NOT NULL,
  adjustment_cents bigint NOT NULL,
  ledger_cents bigint NOT NULL,
  difference_cents bigint NOT NULL,
  summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(period_end>period_start)
);

CREATE TABLE IF NOT EXISTS fiscal.nfse_document(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  invoice_id uuid NOT NULL REFERENCES billing.invoice(id) ON DELETE CASCADE,
  municipality_ibge text,
  provider text,
  provider_document_id text,
  status text NOT NULL DEFAULT 'REQUESTED' CHECK(status IN ('REQUESTED','PROCESSING','AUTHORIZED','REJECTED','CANCELLED','NOT_APPLICABLE')),
  request_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  response_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text NOT NULL,
  requested_by text NOT NULL,
  requested_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,idempotency_key)
);

CREATE TABLE IF NOT EXISTS support.customer_success_account(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  owner_ref text,
  health text NOT NULL DEFAULT 'UNKNOWN' CHECK(health IN ('UNKNOWN','HEALTHY','WATCH','AT_RISK')),
  lifecycle_stage text NOT NULL DEFAULT 'ONBOARDING' CHECK(lifecycle_stage IN ('ONBOARDING','ACTIVE','EXPANSION','RENEWAL','CHURN_RISK','CHURNED')),
  next_review_at timestamptz,
  notes jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_by text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id)
);

CREATE TABLE IF NOT EXISTS support.support_session(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  requested_by text NOT NULL,
  approved_by text,
  target_subject text,
  scopes text[] NOT NULL DEFAULT '{}',
  reason text NOT NULL,
  status text NOT NULL DEFAULT 'PENDING_APPROVAL' CHECK(status IN ('PENDING_APPROVAL','APPROVED','ACTIVE','ENDED','REJECTED','EXPIRED')),
  requested_at timestamptz NOT NULL DEFAULT now(),
  approved_at timestamptz,
  started_at timestamptz,
  ended_at timestamptz,
  expires_at timestamptz NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK(approved_by IS NULL OR approved_by<>requested_by)
);

CREATE TABLE IF NOT EXISTS support.impersonation_event(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  support_session_id uuid NOT NULL REFERENCES support.support_session(id) ON DELETE CASCADE,
  actor text NOT NULL,
  target_subject text,
  action text NOT NULL CHECK(action IN ('START','STOP','EXPIRE','DENY')),
  scopes text[] NOT NULL DEFAULT '{}',
  reason text NOT NULL,
  request_id text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cms.media_asset(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  object_key text NOT NULL UNIQUE,
  media_type text NOT NULL,
  sha256 text NOT NULL,
  alt_text text,
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','ARCHIVED')),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cms.redirect(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  source_path text NOT NULL UNIQUE,
  target_path text NOT NULL,
  http_status integer NOT NULL DEFAULT 308 CHECK(http_status IN (301,302,307,308)),
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','INACTIVE')),
  created_by text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cms.form(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  code text NOT NULL UNIQUE,
  title text NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','ACTIVE','INACTIVE')),
  schema jsonb NOT NULL DEFAULT '{}'::jsonb,
  destination jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cms.form_submission(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  form_id uuid NOT NULL REFERENCES cms.form(id) ON DELETE CASCADE,
  idempotency_key text NOT NULL,
  payload jsonb NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  submitted_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(form_id,idempotency_key)
);

CREATE TABLE IF NOT EXISTS product.analytics_event(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  event_name text NOT NULL,
  subject_hash text,
  session_hash text,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  idempotency_key text NOT NULL,
  UNIQUE(tenant_id,idempotency_key)
);

CREATE TABLE IF NOT EXISTS product.cohort_definition(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  code text NOT NULL,
  name text NOT NULL,
  definition jsonb NOT NULL,
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','INACTIVE')),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,code)
);

CREATE TABLE IF NOT EXISTS product.experiment(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  code text NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','RUNNING','PAUSED','COMPLETED')),
  variants jsonb NOT NULL,
  allocation_percent numeric(5,2) NOT NULL DEFAULT 100 CHECK(allocation_percent>=0 AND allocation_percent<=100),
  started_at timestamptz,
  ended_at timestamptz,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,code)
);

CREATE TABLE IF NOT EXISTS product.experiment_assignment(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  experiment_id uuid NOT NULL REFERENCES product.experiment(id) ON DELETE CASCADE,
  subject_hash text NOT NULL,
  variant text NOT NULL,
  bucket numeric(6,3) NOT NULL,
  assigned_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(experiment_id,subject_hash)
);

CREATE TABLE IF NOT EXISTS product.feature_flag_target(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  feature_flag_id uuid NOT NULL REFERENCES product.feature_flag(id) ON DELETE CASCADE,
  enabled boolean NOT NULL DEFAULT true,
  variant text,
  rollout_percent numeric(5,2) NOT NULL DEFAULT 100 CHECK(rollout_percent>=0 AND rollout_percent<=100),
  configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_by text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,feature_flag_id)
);

CREATE TABLE IF NOT EXISTS ai_ops.usage_cost(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  trace_id text,
  provider text,
  model text NOT NULL,
  input_tokens bigint NOT NULL DEFAULT 0 CHECK(input_tokens>=0),
  output_tokens bigint NOT NULL DEFAULT 0 CHECK(output_tokens>=0),
  input_rate_micros_per_million bigint NOT NULL DEFAULT 0 CHECK(input_rate_micros_per_million>=0),
  output_rate_micros_per_million bigint NOT NULL DEFAULT 0 CHECK(output_rate_micros_per_million>=0),
  cost_micros bigint NOT NULL CHECK(cost_micros>=0),
  currency char(3) NOT NULL DEFAULT 'USD',
  idempotency_key text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,idempotency_key)
);

CREATE TABLE IF NOT EXISTS release.rollback_event(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  environment text NOT NULL,
  deployment_id uuid NOT NULL REFERENCES release.deployment(id),
  rollback_to_deployment_id uuid NOT NULL REFERENCES release.deployment(id),
  status text NOT NULL DEFAULT 'PENDING_APPROVAL' CHECK(status IN ('PENDING_APPROVAL','APPROVED','EXECUTED','REJECTED')),
  requested_by text NOT NULL,
  approved_by text,
  reason text NOT NULL,
  requested_at timestamptz NOT NULL DEFAULT now(),
  approved_at timestamptz,
  executed_at timestamptz,
  CHECK(deployment_id<>rollback_to_deployment_id),
  CHECK(approved_by IS NULL OR approved_by<>requested_by)
);

CREATE TABLE IF NOT EXISTS ops.backup_run(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  scope text NOT NULL,
  environment text NOT NULL,
  status text NOT NULL CHECK(status IN ('STARTED','SUCCEEDED','FAILED')),
  backup_ref text,
  checksum_manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  size_bytes bigint CHECK(size_bytes IS NULL OR size_bytes>=0),
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  error text,
  idempotency_key text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS ops.restore_run(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  backup_run_id uuid REFERENCES ops.backup_run(id) ON DELETE SET NULL,
  scope text NOT NULL,
  environment text NOT NULL,
  status text NOT NULL CHECK(status IN ('STARTED','SUCCEEDED','FAILED')),
  target_ref text,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  error text,
  idempotency_key text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS ops.dr_drill(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  environment text NOT NULL,
  status text NOT NULL CHECK(status IN ('PLANNED','RUNNING','PASSED','FAILED')),
  scenario text NOT NULL,
  rpo_seconds integer CHECK(rpo_seconds IS NULL OR rpo_seconds>=0),
  rto_seconds integer CHECK(rto_seconds IS NULL OR rto_seconds>=0),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  idempotency_key text NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS billing_invoice_tenant_status_idx ON billing.invoice(tenant_id,status,due_at);
CREATE INDEX IF NOT EXISTS billing_dunning_tenant_idx ON billing.dunning_case(tenant_id,status,next_attempt_at);
CREATE INDEX IF NOT EXISTS billing_adjustment_payment_idx ON billing.adjustment(tenant_id,payment_id,created_at);
CREATE INDEX IF NOT EXISTS fiscal_nfse_tenant_idx ON fiscal.nfse_document(tenant_id,status,requested_at DESC);
CREATE INDEX IF NOT EXISTS support_session_tenant_idx ON support.support_session(tenant_id,status,expires_at);
CREATE INDEX IF NOT EXISTS analytics_event_tenant_name_idx ON product.analytics_event(tenant_id,event_name,occurred_at DESC);
CREATE INDEX IF NOT EXISTS ai_cost_tenant_model_idx ON ai_ops.usage_cost(tenant_id,model,occurred_at DESC);
CREATE INDEX IF NOT EXISTS ops_backup_latest_idx ON ops.backup_run(environment,scope,started_at DESC);
CREATE INDEX IF NOT EXISTS ops_restore_latest_idx ON ops.restore_run(environment,scope,started_at DESC);

DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT * FROM (VALUES
    ('admin','idempotency_record'),('catalog','service_contract'),('billing','subscription_add_on'),('billing','invoice'),('billing','invoice_line'),
    ('billing','dunning_case'),('billing','adjustment'),('billing','reconciliation_run'),('fiscal','nfse_document'),('support','customer_success_account'),
    ('support','support_session'),('support','impersonation_event'),('product','analytics_event'),('product','cohort_definition'),('product','experiment'),
    ('product','experiment_assignment'),('product','feature_flag_target'),('ai_ops','usage_cost')
  ) AS x(schemaname,tablename)
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_or_control_admin ON %I.%I',r.schemaname,r.tablename);
    EXECUTE format('CREATE POLICY tenant_or_control_admin ON %I.%I USING (tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid OR current_setting(''app.control_admin'',true)=''true'') WITH CHECK (tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid OR current_setting(''app.control_admin'',true)=''true'')',r.schemaname,r.tablename);
  END LOOP;
END $$;

CREATE OR REPLACE FUNCTION admin.reject_append_only_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION '% is append-only',TG_TABLE_SCHEMA||'.'||TG_TABLE_NAME; END $$;
DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT * FROM (VALUES ('billing','ledger_entry'),('billing','adjustment'),('admin','audit_event'),('support','impersonation_event'),('ai_ops','usage_cost')) AS x(schemaname,tablename)
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS append_only_guard ON %I.%I',r.schemaname,r.tablename);
    EXECUTE format('CREATE TRIGGER append_only_guard BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION admin.reject_append_only_mutation()',r.schemaname,r.tablename);
  END LOOP;
END $$;

GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA tenant,catalog,billing,fiscal,cms,support,product,ops,release,admin,ai_ops TO lotediretor_control_app,lotediretor_control_worker;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA tenant,catalog,billing,fiscal,cms,support,product,ops,release,admin,ai_ops TO lotediretor_control_app,lotediretor_control_worker;
