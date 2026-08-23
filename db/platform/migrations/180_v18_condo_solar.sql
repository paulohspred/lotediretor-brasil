-- v18: Condomínio 360 operational workflows + Solar 2D/3D preliminary design.
-- Private operational tables are tenant-isolated; catalog/regulatory tables may be global.

-- ------------------------- Condomínio 360 -------------------------
-- Existing rule rows receive provenance for deterministic extraction/deliberation.
ALTER TABLE condo.rule ADD COLUMN IF NOT EXISTS extraction_method text;
ALTER TABLE condo.rule ADD COLUMN IF NOT EXISTS confidence numeric;
ALTER TABLE condo.rule ADD COLUMN IF NOT EXISTS superseded_by uuid REFERENCES condo.rule(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS condo.building(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  code text NOT NULL,
  name text NOT NULL,
  floors integer,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(condominium_id,code)
);

CREATE TABLE IF NOT EXISTS condo.unit(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  building_id uuid REFERENCES condo.building(id) ON DELETE SET NULL,
  code text NOT NULL,
  kind text NOT NULL DEFAULT 'UNIT',
  floor_label text,
  private_area_m2 numeric,
  fraction numeric,
  status text NOT NULL DEFAULT 'ACTIVE',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(condominium_id,code)
);

CREATE TABLE IF NOT EXISTS condo.common_area(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  code text NOT NULL,
  name text NOT NULL,
  kind text NOT NULL DEFAULT 'OTHER',
  area_m2 numeric,
  usage_policy text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(condominium_id,code)
);

CREATE TABLE IF NOT EXISTS condo.work_request(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  unit_id uuid REFERENCES condo.unit(id) ON DELETE SET NULL,
  common_area_id uuid REFERENCES condo.common_area(id) ON DELETE SET NULL,
  title text NOT NULL,
  description text,
  work_type text NOT NULL DEFAULT 'REFORM',
  status text NOT NULL DEFAULT 'DRAFT',
  art_rrt_reference text,
  technical_responsible text,
  submitted_by text,
  reviewed_by text,
  submitted_at timestamptz,
  reviewed_at timestamptz,
  decision_reason text,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(unit_id IS NOT NULL OR common_area_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS condo.assembly(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  kind text NOT NULL DEFAULT 'ASSEMBLY',
  title text NOT NULL,
  scheduled_at timestamptz NOT NULL,
  held_at timestamptz,
  status text NOT NULL DEFAULT 'SCHEDULED',
  quorum_rule jsonb NOT NULL DEFAULT '{}'::jsonb,
  document_id uuid REFERENCES condo.document(id) ON DELETE SET NULL,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS condo.agenda_item(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  assembly_id uuid NOT NULL REFERENCES condo.assembly(id) ON DELETE CASCADE,
  ordinal integer NOT NULL,
  title text NOT NULL,
  description text,
  required_quorum jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'OPEN',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(assembly_id,ordinal)
);

CREATE TABLE IF NOT EXISTS condo.decision(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  assembly_id uuid REFERENCES condo.assembly(id) ON DELETE SET NULL,
  agenda_item_id uuid REFERENCES condo.agenda_item(id) ON DELETE SET NULL,
  title text NOT NULL,
  decision_text text NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT',
  effective_from timestamptz,
  effective_to timestamptz,
  generates_rule boolean NOT NULL DEFAULT false,
  generated_rule_id uuid REFERENCES condo.rule(id) ON DELETE SET NULL,
  source_locator text,
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS condo.vote_summary(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  agenda_item_id uuid NOT NULL REFERENCES condo.agenda_item(id) ON DELETE CASCADE,
  eligible_count integer,
  present_count integer,
  favorable_count integer NOT NULL DEFAULT 0,
  contrary_count integer NOT NULL DEFAULT 0,
  abstention_count integer NOT NULL DEFAULT 0,
  fraction_favorable numeric,
  quorum_result text NOT NULL DEFAULT 'PENDING',
  methodology jsonb NOT NULL DEFAULT '{}'::jsonb,
  calculated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(agenda_item_id)
);

CREATE TABLE IF NOT EXISTS condo.maintenance_item(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  common_area_id uuid REFERENCES condo.common_area(id) ON DELETE SET NULL,
  system_code text NOT NULL,
  title text NOT NULL,
  interval_days integer,
  last_done_at date,
  next_due_at date,
  status text NOT NULL DEFAULT 'ACTIVE',
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS condo.occurrence(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  unit_id uuid REFERENCES condo.unit(id) ON DELETE SET NULL,
  category text NOT NULL,
  title text NOT NULL,
  description text,
  status text NOT NULL DEFAULT 'OPEN',
  severity text NOT NULL DEFAULT 'LOW',
  opened_by text,
  reviewed_by text,
  resolution text,
  defense_due_at timestamptz,
  closed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS condo.compliance_item(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  code text NOT NULL,
  title text NOT NULL,
  category text NOT NULL,
  status text NOT NULL DEFAULT 'PENDING',
  due_at date,
  responsible text,
  source_rule_id uuid REFERENCES condo.rule(id) ON DELETE SET NULL,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(condominium_id,code)
);

CREATE INDEX IF NOT EXISTS condo_unit_condo_idx ON condo.unit(condominium_id,status,code);
CREATE INDEX IF NOT EXISTS condo_work_condo_idx ON condo.work_request(condominium_id,status,created_at DESC);
CREATE INDEX IF NOT EXISTS condo_assembly_condo_idx ON condo.assembly(condominium_id,scheduled_at DESC);
CREATE INDEX IF NOT EXISTS condo_maintenance_due_idx ON condo.maintenance_item(condominium_id,next_due_at,status);
CREATE INDEX IF NOT EXISTS condo_occurrence_idx ON condo.occurrence(condominium_id,status,severity,created_at DESC);

-- ------------------------- Solar 360 -------------------------
CREATE TABLE IF NOT EXISTS solar.site(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL REFERENCES solar.project(id) ON DELETE CASCADE,
  kind text NOT NULL DEFAULT 'ROOF',
  name text NOT NULL DEFAULT 'Site principal',
  municipality_ibge text,
  latitude double precision,
  longitude double precision,
  geom geometry(Geometry,4326),
  elevation_m numeric,
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  data_quality jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS solar_site_geom_gix ON solar.site USING gist(geom);

CREATE TABLE IF NOT EXISTS solar.surface(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  site_id uuid NOT NULL REFERENCES solar.site(id) ON DELETE CASCADE,
  code text NOT NULL,
  kind text NOT NULL DEFAULT 'ROOF',
  geom geometry(Polygon,4326),
  local_frame jsonb NOT NULL DEFAULT '{}'::jsonb,
  area_m2 numeric,
  pitch_deg numeric,
  azimuth_deg numeric,
  usable_fraction numeric NOT NULL DEFAULT 1 CHECK(usable_fraction>0 AND usable_fraction<=1),
  source_kind text NOT NULL DEFAULT 'USER',
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  confidence_status text NOT NULL DEFAULT 'PENDING',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(site_id,code)
);
CREATE INDEX IF NOT EXISTS solar_surface_geom_gix ON solar.surface USING gist(geom);

CREATE TABLE IF NOT EXISTS solar.obstacle(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  surface_id uuid NOT NULL REFERENCES solar.surface(id) ON DELETE CASCADE,
  kind text NOT NULL DEFAULT 'OTHER',
  name text,
  geom geometry(Polygon,4326),
  local_rect jsonb NOT NULL DEFAULT '{}'::jsonb,
  height_m numeric,
  clearance_m numeric NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS solar_obstacle_geom_gix ON solar.obstacle USING gist(geom);

CREATE TABLE IF NOT EXISTS solar.module_catalog(
  code text PRIMARY KEY,
  manufacturer text,
  model text NOT NULL,
  watts numeric NOT NULL CHECK(watts>0),
  width_m numeric NOT NULL CHECK(width_m>0),
  height_m numeric NOT NULL CHECK(height_m>0),
  efficiency numeric,
  source_url text,
  datasheet_sha256 text,
  status text NOT NULL DEFAULT 'ACTIVE',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS solar.inverter_catalog(
  code text PRIMARY KEY,
  manufacturer text,
  model text NOT NULL,
  ac_kw numeric NOT NULL CHECK(ac_kw>0),
  max_dc_kw numeric,
  mppt_count integer,
  source_url text,
  datasheet_sha256 text,
  status text NOT NULL DEFAULT 'ACTIVE',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS solar.layout(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL REFERENCES solar.project(id) ON DELETE CASCADE,
  site_id uuid NOT NULL REFERENCES solar.site(id) ON DELETE CASCADE,
  surface_id uuid REFERENCES solar.surface(id) ON DELETE SET NULL,
  scenario_id uuid REFERENCES solar.scenario(id) ON DELETE SET NULL,
  name text NOT NULL,
  status text NOT NULL DEFAULT 'PRELIMINARY',
  module_code text REFERENCES solar.module_catalog(code),
  inverter_code text REFERENCES solar.inverter_catalog(code),
  orientation text NOT NULL DEFAULT 'PORTRAIT',
  panel_count integer NOT NULL DEFAULT 0,
  dc_kwp numeric NOT NULL DEFAULT 0,
  local_frame jsonb NOT NULL DEFAULT '{}'::jsonb,
  layout_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  engine_version text NOT NULL,
  seed text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS solar.layout_panel(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  layout_id uuid NOT NULL REFERENCES solar.layout(id) ON DELETE CASCADE,
  ordinal integer NOT NULL,
  surface_id uuid REFERENCES solar.surface(id) ON DELETE SET NULL,
  x_m numeric NOT NULL,
  y_m numeric NOT NULL,
  width_m numeric NOT NULL,
  height_m numeric NOT NULL,
  rotation_deg numeric NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'PLACED',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(layout_id,ordinal)
);
CREATE INDEX IF NOT EXISTS solar_layout_project_idx ON solar.layout(project_id,created_at DESC);
CREATE INDEX IF NOT EXISTS solar_layout_panel_idx ON solar.layout_panel(layout_id,ordinal);

CREATE TABLE IF NOT EXISTS solar.bill_snapshot(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL REFERENCES solar.project(id) ON DELETE CASCADE,
  reference_month date NOT NULL,
  consumption_kwh numeric NOT NULL CHECK(consumption_kwh>=0),
  billed_energy_brl numeric,
  total_bill_brl numeric,
  tariff_group text,
  distributor text,
  origin text NOT NULL DEFAULT 'USER_ENTERED',
  document_id uuid,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(project_id,reference_month,origin)
);

CREATE TABLE IF NOT EXISTS solar.regulation_snapshot(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid,
  code text NOT NULL,
  title text NOT NULL,
  authority text NOT NULL,
  valid_from date NOT NULL,
  valid_to date,
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'CANDIDATE',
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(code,valid_from,tenant_id)
);

CREATE TABLE IF NOT EXISTS solar.energy_balance(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL REFERENCES solar.project(id) ON DELETE CASCADE,
  scenario_id uuid REFERENCES solar.scenario(id) ON DELETE SET NULL,
  reference_year integer NOT NULL,
  consumption_monthly_kwh numeric[] NOT NULL,
  generation_monthly_kwh numeric[] NOT NULL,
  self_consumption_monthly_kwh numeric[] NOT NULL,
  injected_monthly_kwh numeric[] NOT NULL,
  grid_purchase_monthly_kwh numeric[] NOT NULL,
  assumptions jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Seed equipment is explicitly DEMO/REFERENCE and cannot be presented as a current commercial datasheet.
INSERT INTO solar.module_catalog(code,manufacturer,model,watts,width_m,height_m,efficiency,status,metadata)
VALUES('DEMO-MOD-550','REFERENCE','Módulo de referência 550 W',550,1.134,2.278,null,'REFERENCE','{"dataClass":"DEMO_REFERENCE","notCommercialRecommendation":true}'::jsonb)
ON CONFLICT(code) DO NOTHING;
INSERT INTO solar.inverter_catalog(code,manufacturer,model,ac_kw,max_dc_kw,mppt_count,status,metadata)
VALUES('DEMO-INV-10K','REFERENCE','Inversor de referência 10 kW',10,15,2,'REFERENCE','{"dataClass":"DEMO_REFERENCE","notCommercialRecommendation":true}'::jsonb)
ON CONFLICT(code) DO NOTHING;

INSERT INTO report.template(code,version,title,subject_types,section_order,status)
VALUES
 ('CONDO360_360',1,'Condomínio 360 — Regras, governança, obras e compliance',ARRAY['condominium'],
  '["condo_cover","condo_documents","condo_rules","condo_units","condo_works","condo_assemblies","condo_maintenance","condo_occurrences","condo_compliance","condo_evidence","condo_limitations"]'::jsonb,'ACTIVE'),
 ('SOLAR360_360',1,'Energia Solar 360 — Estudo preliminar técnico-financeiro',ARRAY['solar_project'],
  '["solar_cover","solar_sources","solar_site","solar_surfaces","solar_sun","solar_equipment","solar_layout","solar_generation","solar_consumption","solar_tariff","solar_finance","solar_connection","solar_constraints","solar_evidence","solar_limitations"]'::jsonb,'ACTIVE')
ON CONFLICT(code) DO UPDATE SET version=excluded.version,title=excluded.title,subject_types=excluded.subject_types,section_order=excluded.section_order,status='ACTIVE',updated_at=now();

DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT * FROM (VALUES
    ('condo','building'),('condo','unit'),('condo','common_area'),('condo','work_request'),
    ('condo','assembly'),('condo','agenda_item'),('condo','decision'),('condo','vote_summary'),
    ('condo','maintenance_item'),('condo','occurrence'),('condo','compliance_item'),
    ('solar','site'),('solar','surface'),('solar','obstacle'),('solar','layout'),('solar','layout_panel'),
    ('solar','bill_snapshot'),('solar','energy_balance')
  ) AS x(schemaname,tablename)
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I.%I',r.schemaname,r.tablename);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I.%I USING (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',r.schemaname,r.tablename);
  END LOOP;
END $$;

ALTER TABLE solar.regulation_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE solar.regulation_snapshot FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS solar_regulation_visibility ON solar.regulation_snapshot;
CREATE POLICY solar_regulation_visibility ON solar.regulation_snapshot
USING (tenant_id IS NULL OR tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid);

GRANT SELECT,INSERT,UPDATE,DELETE ON
  condo.building,condo.unit,condo.common_area,condo.work_request,condo.assembly,condo.agenda_item,
  condo.decision,condo.vote_summary,condo.maintenance_item,condo.occurrence,condo.compliance_item,
  solar.site,solar.surface,solar.obstacle,solar.layout,solar.layout_panel,solar.bill_snapshot,solar.energy_balance
TO lotediretor_app,lotediretor_worker;
GRANT SELECT ON solar.module_catalog,solar.inverter_catalog TO lotediretor_app,lotediretor_worker;
GRANT SELECT,INSERT,UPDATE,DELETE ON solar.regulation_snapshot TO lotediretor_app,lotediretor_worker;

UPDATE core.module SET status='V18_CONDO_SOLAR' WHERE code IN ('condominio','energia-solar');
