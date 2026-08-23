CREATE SCHEMA IF NOT EXISTS tiles;
CREATE SCHEMA IF NOT EXISTS ingest;

CREATE TABLE IF NOT EXISTS core.file_object(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  object_key text NOT NULL UNIQUE,
  bucket text NOT NULL,
  filename text NOT NULL,
  content_type text,
  size_bytes bigint NOT NULL CHECK(size_bytes >= 0),
  sha256 text NOT NULL,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE condo.document ADD COLUMN IF NOT EXISTS processing_status text NOT NULL DEFAULT 'PENDING';
ALTER TABLE condo.document ADD COLUMN IF NOT EXISTS processed_at timestamptz;
ALTER TABLE condo.document ADD COLUMN IF NOT EXISTS processing_error text;
ALTER TABLE municipality.document ADD COLUMN IF NOT EXISTS processing_status text NOT NULL DEFAULT 'PENDING';
ALTER TABLE municipality.document ADD COLUMN IF NOT EXISTS processed_at timestamptz;
ALTER TABLE municipality.document ADD COLUMN IF NOT EXISTS processing_error text;

CREATE TABLE IF NOT EXISTS ingest.document_job(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  domain text NOT NULL,
  document_id uuid NOT NULL,
  object_key text NOT NULL,
  sha256 text NOT NULL,
  language text NOT NULL DEFAULT 'por',
  status text NOT NULL DEFAULT 'QUEUED',
  attempts int NOT NULL DEFAULT 0,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  error text,
  UNIQUE(domain,document_id)
);
CREATE TABLE IF NOT EXISTS ingest.document_text(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  domain text NOT NULL,
  document_id uuid NOT NULL,
  chunk_index int NOT NULL,
  text_content text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(domain,document_id,chunk_index)
);

CREATE OR REPLACE VIEW tiles.parcel AS
SELECT id,municipality_ibge,official_identifier,geom
FROM geo.parcel
WHERE tenant_id IS NULL AND superseded_at IS NULL;

CREATE OR REPLACE VIEW tiles.zone AS
SELECT id,municipality_ibge,code,name,geom
FROM planning.zone
WHERE valid_to IS NULL OR valid_to > now();

DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT schemaname,tablename FROM pg_tables WHERE (schemaname,tablename) IN (('core','file_object'),('ingest','document_job'),('ingest','document_text')) LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I.%I',r.schemaname,r.tablename);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I.%I USING (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',r.schemaname,r.tablename);
  END LOOP;
END $$;

UPDATE core.module SET status='V6_INTEGRATED' WHERE code IN ('imovel360','re-rural','condominio','energia-solar','ai-tec','prefeitura','relatorios');
