ALTER TABLE solar.project ADD COLUMN IF NOT EXISTS name text;
ALTER TABLE aitec.project ADD COLUMN IF NOT EXISTS parcel_id uuid REFERENCES geo.parcel(id);

CREATE TABLE IF NOT EXISTS solar.scenario(
  id uuid PRIMARY KEY DEFAULT uuidv7(),tenant_id uuid NOT NULL,project_id uuid NOT NULL REFERENCES solar.project(id) ON DELETE CASCADE,
  name text NOT NULL,panel_count int NOT NULL CHECK(panel_count>0),panel_watts numeric NOT NULL CHECK(panel_watts>0),specific_yield_kwh_per_kwp numeric,
  tariff_brl_per_kwh numeric,capex_cents bigint,status text NOT NULL DEFAULT 'DRAFT',result jsonb NOT NULL DEFAULT '{}'::jsonb,created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS aitec.constraint_snapshot(
  id uuid PRIMARY KEY DEFAULT uuidv7(),tenant_id uuid NOT NULL,project_id uuid NOT NULL REFERENCES aitec.project(id) ON DELETE CASCADE,
  parcel_id uuid REFERENCES geo.parcel(id),base_date date NOT NULL DEFAULT current_date,constraints jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_rule_ids uuid[] NOT NULL DEFAULT '{}',created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS aitec.unit_program(
  id uuid PRIMARY KEY DEFAULT uuidv7(),tenant_id uuid NOT NULL,project_id uuid NOT NULL REFERENCES aitec.project(id) ON DELETE CASCADE,
  unit_type text NOT NULL,target_area_m2 numeric NOT NULL,quantity int NOT NULL,metadata jsonb NOT NULL DEFAULT '{}'::jsonb,created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS aitec.parking_result(
  id uuid PRIMARY KEY DEFAULT uuidv7(),tenant_id uuid NOT NULL,scenario_id uuid NOT NULL REFERENCES aitec.scenario(id) ON DELETE CASCADE,
  required_spaces int,provided_spaces int,area_m2 numeric,assumptions jsonb NOT NULL DEFAULT '{}'::jsonb,created_at timestamptz NOT NULL DEFAULT now()
);

DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT schemaname,tablename FROM pg_tables WHERE (schemaname,tablename) IN (('solar','scenario'),('aitec','constraint_snapshot'),('aitec','unit_program'),('aitec','parking_result')) LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I.%I',r.schemaname,r.tablename);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I.%I USING (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',r.schemaname,r.tablename);
  END LOOP;
END $$;

UPDATE core.module SET status='V5_OPERATIONAL' WHERE code IN ('energia-solar','ai-tec');
