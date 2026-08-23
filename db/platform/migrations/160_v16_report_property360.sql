-- v16: structured Report Engine + deeper Imóvel 360 workflow.
CREATE TABLE IF NOT EXISTS report.template(
  code text PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  title text NOT NULL,
  subject_types text[] NOT NULL DEFAULT '{}',
  section_order jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE report.report_run ADD COLUMN IF NOT EXISTS template_code text;
ALTER TABLE report.report_run ADD COLUMN IF NOT EXISTS template_version integer;
ALTER TABLE report.report_run ADD COLUMN IF NOT EXISTS renderer_version text;
ALTER TABLE report.report_run ADD COLUMN IF NOT EXISTS confidence_summary jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE report.report_run ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE report.report_run ADD COLUMN IF NOT EXISTS frozen_at timestamptz;

CREATE TABLE IF NOT EXISTS report.section(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  report_run_id uuid NOT NULL REFERENCES report.report_run(id) ON DELETE CASCADE,
  section_code text NOT NULL,
  ordinal integer NOT NULL,
  title text NOT NULL,
  status text NOT NULL CHECK(status IN ('CONFIRMED','CALCULATED','INFERRED','PENDING','CONFLICTING','NOT_AVAILABLE')),
  summary text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(report_run_id,section_code)
);

CREATE TABLE IF NOT EXISTS report.evidence(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  report_run_id uuid NOT NULL REFERENCES report.report_run(id) ON DELETE CASCADE,
  section_code text,
  evidence_type text NOT NULL,
  source_code text,
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  source_document_version_id uuid REFERENCES legal.document_version(id),
  source_locator text,
  url text,
  sha256 text,
  confidence_status text NOT NULL DEFAULT 'PENDING',
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS report.snapshot(
  report_run_id uuid PRIMARY KEY REFERENCES report.report_run(id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL,
  schema_version text NOT NULL,
  payload jsonb NOT NULL,
  sha256 text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS report.share_link(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  report_run_id uuid NOT NULL REFERENCES report.report_run(id) ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,
  audience text NOT NULL DEFAULT 'CLIENT',
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS report_section_run_idx ON report.section(report_run_id,ordinal);
CREATE INDEX IF NOT EXISTS report_evidence_run_idx ON report.evidence(report_run_id,section_code);
CREATE INDEX IF NOT EXISTS report_share_link_run_idx ON report.share_link(report_run_id,expires_at);

ALTER TABLE property360.property ADD COLUMN IF NOT EXISTS address text;
ALTER TABLE property360.property ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE property360.property ADD COLUMN IF NOT EXISTS tags text[] NOT NULL DEFAULT '{}';
ALTER TABLE property360.property ADD COLUMN IF NOT EXISTS attributes jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE property360.property ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS property360.property_note(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  property_id uuid NOT NULL REFERENCES property360.property(id) ON DELETE CASCADE,
  body text NOT NULL,
  tags text[] NOT NULL DEFAULT '{}',
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS property360.diligence(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  property_id uuid REFERENCES property360.property(id) ON DELETE CASCADE,
  development_id uuid REFERENCES property360.development(id) ON DELETE CASCADE,
  title text NOT NULL,
  description text,
  status text NOT NULL DEFAULT 'OPEN',
  priority text NOT NULL DEFAULT 'MEDIUM',
  owner_user_id text,
  due_at timestamptz,
  completed_at timestamptz,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(property_id IS NOT NULL OR development_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS property_note_property_idx ON property360.property_note(property_id,created_at DESC);
CREATE INDEX IF NOT EXISTS property360_diligence_tenant_status_idx ON property360.diligence(tenant_id,status,priority,created_at DESC);

CREATE TABLE IF NOT EXISTS municipality.lab_validation_case(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_ibge text NOT NULL REFERENCES municipality.lab_profile(municipality_ibge) ON DELETE CASCADE,
  case_code text NOT NULL,
  input_kind text NOT NULL,
  input_payload jsonb NOT NULL,
  expected_official_reference text,
  expected_parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'PENDING',
  reviewer text,
  reviewed_at timestamptz,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(municipality_ibge,case_code)
);

INSERT INTO report.template(code,version,title,subject_types,section_order,status)
VALUES(
  'PROPERTY360_360',1,'LoteDiretor Brasil — Ficha 360',ARRAY['analysis','property'],
  '[
    {"code":"cover","title":"Capa e identificação"},
    {"code":"executive","title":"Resumo executivo"},
    {"code":"identification","title":"Identificação física e territorial"},
    {"code":"map","title":"Mapa síntese"},
    {"code":"urban","title":"Enquadramento urbanístico e hierarquia legal"},
    {"code":"uses","title":"Usos permitidos, condicionados e proibidos"},
    {"code":"parameters","title":"Parâmetros urbanísticos"},
    {"code":"potential","title":"Potencial construtivo e cenários"},
    {"code":"instruments","title":"Instrumentos urbanísticos e custos"},
    {"code":"environment","title":"Meio ambiente, vegetação e embargos"},
    {"code":"risk","title":"Riscos físicos, geológicos e climáticos"},
    {"code":"infrastructure","title":"Infraestrutura e utilities"},
    {"code":"mobility","title":"Mobilidade, acessos e melhoramentos"},
    {"code":"heritage","title":"Patrimônio, arqueologia e aviação"},
    {"code":"linear","title":"Mineração, dutos, ferrovias, rodovias e portos"},
    {"code":"amenities","title":"Equipamentos e entorno"},
    {"code":"fiscal_market","title":"Fiscal, cadastro e mercado"},
    {"code":"licensing","title":"Licenças e órgãos de aprovação"},
    {"code":"diligence","title":"Diligências e pendências"},
    {"code":"evidence","title":"Anexo de evidências e incerteza"}
  ]'::jsonb,'ACTIVE')
ON CONFLICT(code) DO UPDATE SET version=excluded.version,title=excluded.title,subject_types=excluded.subject_types,section_order=excluded.section_order,status='ACTIVE',updated_at=now();

DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT * FROM (VALUES
    ('report','section'),('report','evidence'),('report','snapshot'),('report','share_link'),
    ('property360','property_note'),('property360','diligence')
  ) AS x(schemaname,tablename)
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I.%I',r.schemaname,r.tablename);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I.%I USING (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',r.schemaname,r.tablename);
  END LOOP;
END $$;

GRANT SELECT ON report.template TO lotediretor_app,lotediretor_worker;
GRANT SELECT,INSERT,UPDATE,DELETE ON report.section,report.evidence,report.snapshot,report.share_link,property360.property_note,property360.diligence TO lotediretor_app,lotediretor_worker;
GRANT SELECT,INSERT,UPDATE,DELETE ON municipality.lab_validation_case TO lotediretor_app,lotediretor_worker;

UPDATE core.module SET status='V16_REPORT_PROPERTY360' WHERE code IN ('imovel360','relatorios');
