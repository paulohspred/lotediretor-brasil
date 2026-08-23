-- v15: territorial core aligned with Blueprint sections 7-16 and 32.12-32.18.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS environment;
CREATE SCHEMA IF NOT EXISTS risk;
CREATE SCHEMA IF NOT EXISTS mobility;
CREATE SCHEMA IF NOT EXISTS heritage;
CREATE SCHEMA IF NOT EXISTS licensing;

CREATE TABLE IF NOT EXISTS core.asset(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid,
  kind text NOT NULL DEFAULT 'PARCEL',
  municipality_ibge text,
  parcel_id uuid REFERENCES geo.parcel(id),
  canonical_label text,
  status text NOT NULL DEFAULT 'ACTIVE',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS core_asset_municipality_idx ON core.asset(municipality_ibge);

CREATE TABLE IF NOT EXISTS core.asset_identifier(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  asset_id uuid NOT NULL REFERENCES core.asset(id) ON DELETE CASCADE,
  tenant_id uuid,
  identifier_type text NOT NULL,
  identifier_value text NOT NULL,
  authority text,
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  valid_from timestamptz,
  valid_to timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS core_asset_identifier_lookup_idx ON core.asset_identifier(identifier_type,identifier_value);
CREATE UNIQUE INDEX IF NOT EXISTS core_asset_identifier_uq ON core.asset_identifier(asset_id,identifier_type,identifier_value,coalesce(valid_from,'-infinity'::timestamptz));

CREATE TABLE IF NOT EXISTS source.coverage(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  source_id uuid NOT NULL REFERENCES source.registry(id) ON DELETE CASCADE,
  municipality_ibge text,
  dataset_code text NOT NULL,
  scope text NOT NULL DEFAULT 'MUNICIPAL',
  availability_status text NOT NULL DEFAULT 'DISCOVERED',
  ingestion_status text NOT NULL DEFAULT 'NOT_INGESTED',
  access_class text,
  parser_version text,
  last_checked_at timestamptz,
  last_source_update timestamptz,
  evidence_hash text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(source_id,municipality_ibge,dataset_code)
);
CREATE INDEX IF NOT EXISTS source_coverage_municipality_idx ON source.coverage(municipality_ibge,dataset_code);

CREATE TABLE IF NOT EXISTS geo.municipality_boundary(
  municipality_ibge text NOT NULL,
  source_snapshot_id uuid NOT NULL REFERENCES source.snapshot(id),
  geom geometry(MultiPolygon,4326) NOT NULL,
  valid_from timestamptz,
  valid_to timestamptz,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(municipality_ibge,source_snapshot_id)
);
CREATE INDEX IF NOT EXISTS geo_municipality_boundary_gix ON geo.municipality_boundary USING gist(geom);

CREATE TABLE IF NOT EXISTS geo.layer(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  code text NOT NULL UNIQUE,
  title text NOT NULL,
  domain text NOT NULL,
  municipality_ibge text,
  source_id uuid REFERENCES source.registry(id),
  dataset_code text,
  geometry_type text,
  visibility text NOT NULL DEFAULT 'PUBLIC',
  status text NOT NULL DEFAULT 'DISCOVERED',
  style jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS geo.feature(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  layer_id uuid NOT NULL REFERENCES geo.layer(id) ON DELETE CASCADE,
  tenant_id uuid,
  source_snapshot_id uuid NOT NULL REFERENCES source.snapshot(id),
  official_identifier text,
  geom geometry(Geometry,4326) NOT NULL,
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  valid_from timestamptz,
  valid_to timestamptz,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  superseded_at timestamptz
);
CREATE INDEX IF NOT EXISTS geo_feature_geom_gix ON geo.feature USING gist(geom);
CREATE INDEX IF NOT EXISTS geo_feature_layer_idx ON geo.feature(layer_id,source_snapshot_id);
CREATE INDEX IF NOT EXISTS geo_feature_official_identifier_idx ON geo.feature(official_identifier);

CREATE TABLE IF NOT EXISTS geo.address_index(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_ibge text,
  parcel_id uuid REFERENCES geo.parcel(id),
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  formatted_address text NOT NULL,
  normalized_address text NOT NULL,
  postal_code text,
  geom geometry(Point,4326),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  valid_from timestamptz,
  valid_to timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS geo_address_index_trgm ON geo.address_index USING gin(normalized_address gin_trgm_ops);
CREATE INDEX IF NOT EXISTS geo_address_index_geom_gix ON geo.address_index USING gist(geom);

CREATE TABLE IF NOT EXISTS legal.article(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  document_version_id uuid NOT NULL REFERENCES legal.document_version(id) ON DELETE CASCADE,
  parent_article_id uuid REFERENCES legal.article(id),
  hierarchy_path text NOT NULL,
  article_type text NOT NULL DEFAULT 'ARTICLE',
  label text,
  heading text,
  body_text text NOT NULL,
  ordinal integer,
  source_locator text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(document_version_id,hierarchy_path)
);
CREATE INDEX IF NOT EXISTS legal_article_text_trgm ON legal.article USING gin(body_text gin_trgm_ops);

CREATE TABLE IF NOT EXISTS legal.relation(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  from_document_version_id uuid NOT NULL REFERENCES legal.document_version(id) ON DELETE CASCADE,
  to_document_version_id uuid REFERENCES legal.document_version(id),
  relation_type text NOT NULL,
  source_locator text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS legal.annex(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  document_version_id uuid NOT NULL REFERENCES legal.document_version(id) ON DELETE CASCADE,
  kind text NOT NULL DEFAULT 'ANNEX',
  title text,
  object_key text,
  sha256 text,
  source_locator text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS legal.conflict(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_ibge text NOT NULL,
  zone_code text,
  parameter text,
  rule_ids uuid[] NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'OPEN',
  reason text NOT NULL,
  resolution text,
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analysis.spatial_relation(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  run_id uuid NOT NULL REFERENCES analysis.run(id) ON DELETE CASCADE,
  relation_type text NOT NULL,
  layer_code text NOT NULL,
  feature_id uuid REFERENCES geo.feature(id),
  distance_m numeric,
  intersection_area_m2 numeric,
  intersection_ratio numeric,
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS analysis_spatial_relation_run_idx ON analysis.spatial_relation(run_id,layer_code);

CREATE TABLE IF NOT EXISTS analysis.calculation(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  run_id uuid NOT NULL REFERENCES analysis.run(id) ON DELETE CASCADE,
  code text NOT NULL,
  value_numeric numeric,
  value_text text,
  unit text,
  formula text,
  inputs jsonb NOT NULL DEFAULT '{}'::jsonb,
  rule_ids uuid[] NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'CALCULATED',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(run_id,code)
);

CREATE TABLE IF NOT EXISTS analysis.snapshot_ref(
  run_id uuid NOT NULL REFERENCES analysis.run(id) ON DELETE CASCADE,
  source_snapshot_id uuid NOT NULL REFERENCES source.snapshot(id),
  purpose text NOT NULL,
  PRIMARY KEY(run_id,source_snapshot_id,purpose)
);

CREATE TABLE IF NOT EXISTS municipality.lab_profile(
  municipality_ibge text PRIMARY KEY,
  status text NOT NULL DEFAULT 'DISCOVERED',
  source_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  activated_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Generic domain views keep the spatial engine domain-aware while source features remain normalized once.
CREATE OR REPLACE VIEW environment.feature AS SELECT f.*,l.code layer_code,l.title layer_title FROM geo.feature f JOIN geo.layer l ON l.id=f.layer_id WHERE l.domain='ENVIRONMENT';
CREATE OR REPLACE VIEW risk.feature AS SELECT f.*,l.code layer_code,l.title layer_title FROM geo.feature f JOIN geo.layer l ON l.id=f.layer_id WHERE l.domain='RISK';
CREATE OR REPLACE VIEW infra.feature AS SELECT f.*,l.code layer_code,l.title layer_title FROM geo.feature f JOIN geo.layer l ON l.id=f.layer_id WHERE l.domain='INFRA';
CREATE OR REPLACE VIEW mobility.feature AS SELECT f.*,l.code layer_code,l.title layer_title FROM geo.feature f JOIN geo.layer l ON l.id=f.layer_id WHERE l.domain='MOBILITY';
CREATE OR REPLACE VIEW heritage.feature AS SELECT f.*,l.code layer_code,l.title layer_title FROM geo.feature f JOIN geo.layer l ON l.id=f.layer_id WHERE l.domain='HERITAGE';
CREATE OR REPLACE VIEW licensing.feature AS SELECT f.*,l.code layer_code,l.title layer_title FROM geo.feature f JOIN geo.layer l ON l.id=f.layer_id WHERE l.domain='LICENSING';

-- Runtime grants for the new schemas/tables. Migrations remain owner-only.
GRANT USAGE ON SCHEMA environment,risk,mobility,heritage,licensing TO lotediretor_app,lotediretor_worker;
GRANT SELECT ON ALL TABLES IN SCHEMA environment,risk,mobility,heritage,licensing TO lotediretor_app,lotediretor_worker;
GRANT SELECT,INSERT,UPDATE,DELETE ON core.asset,core.asset_identifier,source.coverage,geo.municipality_boundary,geo.layer,geo.feature,geo.address_index,legal.article,legal.relation,legal.annex,legal.conflict,analysis.spatial_relation,analysis.calculation,analysis.snapshot_ref,municipality.lab_profile TO lotediretor_app,lotediretor_worker;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA environment,risk,mobility,heritage,licensing TO lotediretor_app,lotediretor_worker;

-- Public-or-tenant canonical asset/feature rows. Public rows can only be written by workers/owner.
ALTER TABLE core.asset ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.asset FORCE ROW LEVEL SECURITY;
CREATE POLICY core_asset_shared_select ON core.asset FOR SELECT TO lotediretor_app USING (tenant_id IS NULL OR tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
CREATE POLICY core_asset_tenant_insert ON core.asset FOR INSERT TO lotediretor_app WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
CREATE POLICY core_asset_tenant_update ON core.asset FOR UPDATE TO lotediretor_app USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
CREATE POLICY core_asset_tenant_delete ON core.asset FOR DELETE TO lotediretor_app USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);

ALTER TABLE core.asset_identifier ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.asset_identifier FORCE ROW LEVEL SECURITY;
CREATE POLICY core_asset_identifier_shared_select ON core.asset_identifier FOR SELECT TO lotediretor_app USING (tenant_id IS NULL OR tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
CREATE POLICY core_asset_identifier_tenant_insert ON core.asset_identifier FOR INSERT TO lotediretor_app WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
CREATE POLICY core_asset_identifier_tenant_update ON core.asset_identifier FOR UPDATE TO lotediretor_app USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
CREATE POLICY core_asset_identifier_tenant_delete ON core.asset_identifier FOR DELETE TO lotediretor_app USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);

ALTER TABLE geo.feature ENABLE ROW LEVEL SECURITY;
ALTER TABLE geo.feature FORCE ROW LEVEL SECURITY;
CREATE POLICY geo_feature_shared_select ON geo.feature FOR SELECT TO lotediretor_app USING (tenant_id IS NULL OR tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
CREATE POLICY geo_feature_tenant_insert ON geo.feature FOR INSERT TO lotediretor_app WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
CREATE POLICY geo_feature_tenant_update ON geo.feature FOR UPDATE TO lotediretor_app USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
CREATE POLICY geo_feature_tenant_delete ON geo.feature FOR DELETE TO lotediretor_app USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);

-- São Paulo municipality laboratory profile: official discovery only. No dataset is marked ingested/active here.
INSERT INTO source.registry(code,title,authority,access_class,channel,base_url,data_owner,cadence,health,license_terms,provenance)
VALUES
 ('SP_GEOSAMPA_WFS','GeoSampa — WFS','Prefeitura de São Paulo','B','WFS','http://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wfs','Prefeitura de São Paulo','WEEKLY','UNKNOWN','VERIFY_LAYER_METADATA_BEFORE_ACTIVATION','{"official":true,"municipality_ibge":"3550308","discovery":"official GeoSampa tutorial"}'::jsonb),
 ('SP_LEGISLACAO_PDE','Catálogo de Legislação Municipal — PDE','Prefeitura de São Paulo','B','HTML','https://legislacao.prefeitura.sp.gov.br/lei-16050-de-31-de-julho-de-2014/consolidado','Prefeitura de São Paulo','DAILY','UNKNOWN','PUBLIC_WEB_TERMS_REQUIRE_REVIEW','{"official":true,"municipality_ibge":"3550308","law":"16.050/2014","consolidated":true}'::jsonb)
ON CONFLICT(code) DO UPDATE SET title=excluded.title,authority=excluded.authority,channel=excluded.channel,base_url=excluded.base_url,data_owner=excluded.data_owner,provenance=excluded.provenance;

INSERT INTO source.coverage(source_id,municipality_ibge,dataset_code,scope,availability_status,ingestion_status,access_class,metadata)
SELECT id,'3550308',x.dataset_code,'MUNICIPAL','DISCOVERED','NOT_INGESTED',access_class,x.metadata
FROM source.registry r
JOIN (VALUES
 ('SP_GEOSAMPA_WFS','PARCEL', '{"requires_layer_mapping":true}'::jsonb),
 ('SP_GEOSAMPA_WFS','ZONEAMENTO', '{"requires_layer_mapping":true}'::jsonb),
 ('SP_GEOSAMPA_WFS','MUNICIPAL_GIS', '{"requires_layer_mapping":true}'::jsonb),
 ('SP_LEGISLACAO_PDE','PLANO_DIRETOR', '{"law":"16.050/2014","status":"ALTERADO/REVOGADO_PARCIALMENTE"}'::jsonb)
) x(source_code,dataset_code,metadata) ON x.source_code=r.code
ON CONFLICT(source_id,municipality_ibge,dataset_code) DO UPDATE SET metadata=excluded.metadata,updated_at=now();

INSERT INTO municipality.lab_profile(municipality_ibge,status,source_profile,validation_summary)
VALUES('3550308','DISCOVERED',
  '{"name":"São Paulo","uf":"SP","canonical_key":"3550308","sources":["SP_GEOSAMPA_WFS","SP_LEGISLACAO_PDE"],"rule":"No source is promoted without snapshot + QA + human validation."}'::jsonb,
  '{"manual_test_lots_required":10,"gis_layer_mapping":"PENDING","legal_ingestion":"PENDING","production_ready":false}'::jsonb)
ON CONFLICT(municipality_ibge) DO UPDATE SET source_profile=excluded.source_profile,validation_summary=excluded.validation_summary,updated_at=now();
