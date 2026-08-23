ALTER TABLE rural.asset ADD COLUMN IF NOT EXISTS geom geometry(MultiPolygon,4326);
CREATE INDEX IF NOT EXISTS rural_asset_geom_gix ON rural.asset USING gist(geom);

CREATE TABLE IF NOT EXISTS rural.overlap_result(
  id uuid PRIMARY KEY DEFAULT uuidv7(),tenant_id uuid,asset_id uuid NOT NULL REFERENCES rural.asset(id) ON DELETE CASCADE,
  registry_record_id uuid REFERENCES rural.registry_record(id),overlap_type text NOT NULL,overlap_area_m2 numeric,overlap_ratio numeric,
  evidence_id uuid REFERENCES evidence.evidence(id),calculated_at timestamptz NOT NULL DEFAULT now(),metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS rural.monitor(
  id uuid PRIMARY KEY DEFAULT uuidv7(),tenant_id uuid NOT NULL,asset_id uuid NOT NULL REFERENCES rural.asset(id) ON DELETE CASCADE,
  monitor_type text NOT NULL,status text NOT NULL DEFAULT 'ACTIVE',last_checked_at timestamptz,last_change_at timestamptz,
  configuration jsonb NOT NULL DEFAULT '{}'::jsonb,created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS condo.document_chunk(
  id uuid PRIMARY KEY DEFAULT uuidv7(),tenant_id uuid NOT NULL,document_id uuid NOT NULL REFERENCES condo.document(id) ON DELETE CASCADE,
  chunk_index int NOT NULL,text_content text NOT NULL,valid_from timestamptz,valid_to timestamptz,metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(document_id,chunk_index)
);
CREATE TABLE IF NOT EXISTS condo.rule(
  id uuid PRIMARY KEY DEFAULT uuidv7(),tenant_id uuid NOT NULL,condominium_id uuid NOT NULL REFERENCES condo.condominium(id) ON DELETE CASCADE,
  document_id uuid REFERENCES condo.document(id),rule_type text NOT NULL,title text NOT NULL,rule_text text NOT NULL,status text NOT NULL DEFAULT 'CANDIDATE',
  source_locator text,valid_from timestamptz,valid_to timestamptz,reviewed_by text,reviewed_at timestamptz,created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS municipality.document(
  id uuid PRIMARY KEY DEFAULT uuidv7(),municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,title text NOT NULL,
  kind text NOT NULL,object_key text NOT NULL,sha256 text NOT NULL,status text NOT NULL DEFAULT 'UPLOADED',created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS municipality.rule_review(
  id uuid PRIMARY KEY DEFAULT uuidv7(),municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  legal_rule_id uuid NOT NULL REFERENCES legal.rule(id),status text NOT NULL DEFAULT 'PENDING',reviewer_id text,reason text,reviewed_at timestamptz,created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS municipality.ctm_parcel(
  id uuid PRIMARY KEY DEFAULT uuidv7(),municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,cadastral_code text NOT NULL,
  geom geometry(MultiPolygon,4326),attributes jsonb NOT NULL DEFAULT '{}'::jsonb,source_snapshot_id uuid REFERENCES source.snapshot(id),valid_from timestamptz,valid_to timestamptz,
  UNIQUE(municipality_tenant_id,cadastral_code,valid_from)
);
CREATE INDEX IF NOT EXISTS municipality_ctm_geom_gix ON municipality.ctm_parcel USING gist(geom);
CREATE TABLE IF NOT EXISTS municipality.iptu_record(
  id uuid PRIMARY KEY DEFAULT uuidv7(),municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,cadastral_code text NOT NULL,
  reference_year int NOT NULL,land_value_cents bigint,building_value_cents bigint,tax_value_cents bigint,attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(municipality_tenant_id,cadastral_code,reference_year)
);

DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT schemaname,tablename FROM pg_tables
    WHERE (schemaname,tablename) IN (('rural','monitor'),('condo','document_chunk'),('condo','rule'))
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I.%I',r.schemaname,r.tablename);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I.%I USING (tenant_id = nullif(current_setting(''app.tenant_id'', true),'''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'', true),'''')::uuid)',r.schemaname,r.tablename);
  END LOOP;
END $$;

UPDATE core.module SET status='V4_OPERATIONAL' WHERE code IN ('re-rural','condominio','prefeitura');
