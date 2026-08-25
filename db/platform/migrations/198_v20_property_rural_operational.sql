-- v20: operational Imóvel 360 + RE Rural governance plane.
-- Implementation does not auto-homologate external market/registry sources.

CREATE TABLE IF NOT EXISTS property360.avm_methodology(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  version text NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','CALIBRATED','APPROVED','RETIRED')),
  algorithm text NOT NULL,
  min_comparables integer NOT NULL CHECK(min_comparables >= 1),
  max_age_days integer NOT NULL CHECK(max_age_days >= 0),
  parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  calibration_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  calibration_source_snapshot_ids uuid[] NOT NULL DEFAULT '{}',
  valid_from date,
  valid_to date,
  approved_by text,
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,version),
  CHECK(status <> 'APPROVED' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL AND cardinality(calibration_source_snapshot_ids) > 0))
);

ALTER TABLE property360.avm_run ADD COLUMN IF NOT EXISTS methodology_id uuid REFERENCES property360.avm_methodology(id);
ALTER TABLE property360.avm_run ADD COLUMN IF NOT EXISTS base_date date;
ALTER TABLE property360.avm_run ADD COLUMN IF NOT EXISTS source_snapshot_ids uuid[] NOT NULL DEFAULT '{}';
ALTER TABLE property360.avm_run ADD COLUMN IF NOT EXISTS uncertainty jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE property360.avm_run ADD COLUMN IF NOT EXISTS evidence_summary jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS property360.market_series(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  municipality_ibge text NOT NULL,
  neighborhood text,
  development_id uuid REFERENCES property360.development(id) ON DELETE SET NULL,
  period date NOT NULL,
  units_launched integer CHECK(units_launched IS NULL OR units_launched >= 0),
  units_sold integer CHECK(units_sold IS NULL OR units_sold >= 0),
  inventory_end integer CHECK(inventory_end IS NULL OR inventory_end >= 0),
  units_leased integer CHECK(units_leased IS NULL OR units_leased >= 0),
  rental_inventory_end integer CHECK(rental_inventory_end IS NULL OR rental_inventory_end >= 0),
  asking_price_cents_m2 bigint CHECK(asking_price_cents_m2 IS NULL OR asking_price_cents_m2 > 0),
  asking_rent_cents_m2 bigint CHECK(asking_rent_cents_m2 IS NULL OR asking_rent_cents_m2 > 0),
  source_snapshot_id uuid NOT NULL REFERENCES source.snapshot(id),
  data_class text NOT NULL DEFAULT 'OBSERVED' CHECK(data_class IN ('OBSERVED','LICENSED','REPORTED')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS property360_market_series_identity_uq
  ON property360.market_series(
    tenant_id,
    municipality_ibge,
    COALESCE(neighborhood,''),
    COALESCE(development_id,'00000000-0000-0000-0000-000000000000'::uuid),
    period,
    source_snapshot_id
  );
CREATE INDEX IF NOT EXISTS property360_market_series_lookup_idx ON property360.market_series(tenant_id,municipality_ibge,period DESC);

CREATE TABLE IF NOT EXISTS property360.land_prospect_run(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  base_date date NOT NULL,
  objective_spec jsonb NOT NULL,
  input_snapshot jsonb NOT NULL,
  output_snapshot jsonb NOT NULL,
  source_snapshot_ids uuid[] NOT NULL DEFAULT '{}',
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS property360.b2b_api_key(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  name text NOT NULL,
  key_prefix text NOT NULL,
  key_hash text NOT NULL UNIQUE,
  scopes text[] NOT NULL DEFAULT '{}',
  expires_at timestamptz,
  revoked_at timestamptz,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz
);
CREATE INDEX IF NOT EXISTS property360_b2b_key_tenant_idx ON property360.b2b_api_key(tenant_id,revoked_at,expires_at);

CREATE TABLE IF NOT EXISTS rural.connector_catalog(
  code text PRIMARY KEY,
  authority text NOT NULL,
  data_family text NOT NULL,
  legal_notes text,
  external_gate boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rural.connector_config(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  connector_code text NOT NULL REFERENCES rural.connector_catalog(code),
  source_id uuid REFERENCES source.registry(id),
  access_mode text,
  legal_availability text,
  status text NOT NULL DEFAULT 'EXTERNAL_GATE' CHECK(status IN ('EXTERNAL_GATE','CONFIGURED','DISABLED')),
  configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,connector_code)
);

CREATE TABLE IF NOT EXISTS rural.connector_run(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  connector_config_id uuid NOT NULL REFERENCES rural.connector_config(id) ON DELETE CASCADE,
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  run_status text NOT NULL CHECK(run_status IN ('STARTED','SUCCEEDED','FAILED','EVIDENCE_INCOMPLETE')),
  records_received bigint CHECK(records_received IS NULL OR records_received >= 0),
  records_loaded bigint CHECK(records_loaded IS NULL OR records_loaded >= 0),
  request_fingerprint text,
  response_sha256 text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  error text
);
CREATE INDEX IF NOT EXISTS rural_connector_run_latest_idx ON rural.connector_run(tenant_id,connector_config_id,started_at DESC);

CREATE TABLE IF NOT EXISTS rural.golden_case(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  case_code text NOT NULL,
  asset_id uuid REFERENCES rural.asset(id) ON DELETE SET NULL,
  base_date date NOT NULL,
  expected jsonb NOT NULL,
  actual jsonb NOT NULL,
  source_snapshot_ids uuid[] NOT NULL DEFAULT '{}',
  review_status text NOT NULL DEFAULT 'PENDING_EXTERNAL_REVIEW' CHECK(review_status IN ('PENDING_EXTERNAL_REVIEW','EXTERNAL_REVIEW_RECORDED')),
  reviewer text,
  professional_reference text,
  reviewed_at timestamptz,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,case_code)
);

INSERT INTO rural.connector_catalog(code,authority,data_family,legal_notes,external_gate) VALUES
('CAR','SICAR / órgão competente','ENVIRONMENTAL_REGISTRY','Cadastro ambiental não prova domínio.',true),
('SIGEF','INCRA','GEODETIC_REGISTRY','Certificação georreferenciada conserva sua natureza jurídica.',true),
('SNCR','INCRA','RURAL_CADASTRE','Cadastro rural não prova domínio.',true),
('CCIR','INCRA','RURAL_CADASTRE','Certificado cadastral sujeito à fonte oficial vigente.',true),
('CAFIR_CIB','Receita Federal','FISCAL_CADASTRE','Dados fiscais exigem base/autorização juridicamente disponível.',true),
('IBAMA','IBAMA','ENVIRONMENTAL_ENFORCEMENT','Embargos e restrições exigem fonte oficial versionada.',true),
('PRODES','INPE','DEFORESTATION','Monitoramento remoto exige data-base e metodologia da fonte.',true),
('DETER','INPE','DEFORESTATION_ALERT','Alerta não equivale a autuação ou prova dominial.',true),
('FUNAI','FUNAI','INDIGENOUS_LANDS','Interseção espacial não substitui análise jurídica.',true),
('CNUC','MMA','PROTECTED_AREAS','Unidades de conservação exigem categoria e ato vigente.',true),
('INCRA_ASSENTAMENTOS','INCRA','SETTLEMENTS','Assentamentos exigem fonte oficial e temporalidade.',true),
('QUILOMBOLAS','INCRA / órgãos competentes','QUILOMBOLA','Estágio processual deve ser preservado, sem inferência dominial.',true),
('SICOR_BACEN','Banco Central','RURAL_CREDIT','Acesso e uso dependem de disponibilidade e base legal aplicável.',true)
ON CONFLICT(code) DO UPDATE SET authority=excluded.authority,data_family=excluded.data_family,legal_notes=excluded.legal_notes,external_gate=true;

DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT * FROM (VALUES
    ('property360','avm_methodology'),('property360','market_series'),('property360','land_prospect_run'),
    ('rural','connector_config'),('rural','connector_run'),('rural','golden_case')
  ) AS x(schemaname,tablename)
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I.%I',r.schemaname,r.tablename);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I.%I USING (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',r.schemaname,r.tablename);
  END LOOP;
END $$;

-- B2B keys need a SECURITY DEFINER resolver before tenant context is known.
ALTER TABLE property360.b2b_api_key ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON property360.b2b_api_key;
CREATE POLICY tenant_isolation ON property360.b2b_api_key
  USING (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid)
  WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid);

CREATE OR REPLACE FUNCTION property360.resolve_b2b_api_key(p_key_hash text)
RETURNS TABLE(key_id uuid,tenant_id uuid,scopes text[])
LANGUAGE sql SECURITY DEFINER SET search_path=property360,pg_temp AS $$
  SELECT k.id,k.tenant_id,k.scopes
  FROM property360.b2b_api_key k
  WHERE k.key_hash=p_key_hash AND k.revoked_at IS NULL AND (k.expires_at IS NULL OR k.expires_at>now())
  LIMIT 1
$$;
REVOKE ALL ON FUNCTION property360.resolve_b2b_api_key(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION property360.resolve_b2b_api_key(text) TO lotediretor_app;

GRANT SELECT,INSERT,UPDATE,DELETE ON property360.avm_methodology,property360.market_series,property360.land_prospect_run,property360.b2b_api_key TO lotediretor_app,lotediretor_worker;
GRANT SELECT ON rural.connector_catalog TO lotediretor_app,lotediretor_worker;
GRANT SELECT,INSERT,UPDATE,DELETE ON rural.connector_config,rural.connector_run,rural.golden_case TO lotediretor_app,lotediretor_worker;

UPDATE core.module SET status='V20_OPERATIONAL_IMPLEMENTATION' WHERE code IN ('imovel360','re-rural');
