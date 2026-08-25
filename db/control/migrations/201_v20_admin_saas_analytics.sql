-- v20 Admin SaaS follow-up: explicit payment allocation and funnel definitions.
CREATE TABLE IF NOT EXISTS billing.payment_allocation(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  payment_id uuid NOT NULL REFERENCES billing.payment(id) ON DELETE CASCADE,
  invoice_id uuid NOT NULL REFERENCES billing.invoice(id) ON DELETE CASCADE,
  amount_cents bigint NOT NULL CHECK(amount_cents>0),
  idempotency_key text NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS billing_payment_allocation_invoice_idx ON billing.payment_allocation(tenant_id,invoice_id,created_at);

CREATE TABLE IF NOT EXISTS product.funnel_definition(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL REFERENCES tenant.tenant(id) ON DELETE CASCADE,
  code text NOT NULL,
  name text NOT NULL,
  steps jsonb NOT NULL,
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','INACTIVE')),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,code)
);

DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT * FROM (VALUES ('billing','payment_allocation'),('product','funnel_definition')) AS x(schemaname,tablename)
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_or_control_admin ON %I.%I',r.schemaname,r.tablename);
    EXECUTE format('CREATE POLICY tenant_or_control_admin ON %I.%I USING (tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid OR current_setting(''app.control_admin'',true)=''true'') WITH CHECK (tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid OR current_setting(''app.control_admin'',true)=''true'')',r.schemaname,r.tablename);
  END LOOP;
END $$;

DROP TRIGGER IF EXISTS append_only_guard ON billing.payment_allocation;
CREATE TRIGGER append_only_guard BEFORE UPDATE OR DELETE ON billing.payment_allocation FOR EACH ROW EXECUTE FUNCTION admin.reject_append_only_mutation();
GRANT SELECT,INSERT,UPDATE,DELETE ON billing.payment_allocation,product.funnel_definition TO lotediretor_control_app,lotediretor_control_worker;
