-- v19-rc.3: preliminary electrical string/MPPT design with explicit datasheet provenance.
CREATE TABLE IF NOT EXISTS solar.electrical_design(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL REFERENCES solar.project(id) ON DELETE CASCADE,
  layout_id uuid REFERENCES solar.layout(id) ON DELETE SET NULL,
  scenario_id uuid REFERENCES solar.scenario(id) ON DELETE SET NULL,
  module_code text REFERENCES solar.module_catalog(code),
  inverter_code text REFERENCES solar.inverter_catalog(code),
  status text NOT NULL,
  engine_version text NOT NULL,
  input_snapshot jsonb NOT NULL,
  output_snapshot jsonb NOT NULL,
  module_datasheet_sha256 text,
  inverter_datasheet_sha256 text,
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS solar_electrical_design_project_idx ON solar.electrical_design(tenant_id,project_id,created_at DESC);
ALTER TABLE solar.electrical_design ENABLE ROW LEVEL SECURITY;
ALTER TABLE solar.electrical_design FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON solar.electrical_design;
CREATE POLICY tenant_isolation ON solar.electrical_design
USING (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid);
GRANT SELECT,INSERT,UPDATE,DELETE ON solar.electrical_design TO lotediretor_app,lotediretor_worker;

-- PostgreSQL UNIQUE treats NULL values as distinct. Preserve one global regulation
-- row per code/date in addition to tenant-specific rows.
CREATE UNIQUE INDEX IF NOT EXISTS solar_regulation_global_code_date_uidx
ON solar.regulation_snapshot(code,valid_from) WHERE tenant_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS solar_regulation_tenant_code_date_uidx
ON solar.regulation_snapshot(tenant_id,code,valid_from) WHERE tenant_id IS NOT NULL;
