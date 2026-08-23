-- v17 — RE Rural 360: identidade cadastral sem fusão jurídica, monitoring diff,
-- exportações e relatório rural auditável.

CREATE TABLE IF NOT EXISTS rural.registry_identifier(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  asset_id uuid NOT NULL REFERENCES rural.asset(id) ON DELETE CASCADE,
  registry_record_id uuid REFERENCES rural.registry_record(id) ON DELETE CASCADE,
  identifier_type text NOT NULL,
  identifier_value text NOT NULL,
  normalized_value text NOT NULL,
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  status text NOT NULL DEFAULT 'OBSERVED',
  valid_from timestamptz,
  valid_to timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(asset_id,identifier_type,normalized_value,registry_record_id)
);
CREATE INDEX IF NOT EXISTS rural_registry_identifier_lookup_idx ON rural.registry_identifier(identifier_type,normalized_value);

CREATE TABLE IF NOT EXISTS rural.geometry_version(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  asset_id uuid NOT NULL REFERENCES rural.asset(id) ON DELETE CASCADE,
  registry_record_id uuid REFERENCES rural.registry_record(id) ON DELETE CASCADE,
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  geom geometry(Geometry,4326) NOT NULL,
  area_m2 numeric,
  geometry_hash text NOT NULL,
  quality jsonb NOT NULL DEFAULT '{}'::jsonb,
  valid_from timestamptz,
  valid_to timestamptz,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(asset_id,geometry_hash,registry_record_id)
);
CREATE INDEX IF NOT EXISTS rural_geometry_version_gix ON rural.geometry_version USING gist(geom);

CREATE TABLE IF NOT EXISTS rural.identity_link(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  asset_id uuid NOT NULL REFERENCES rural.asset(id) ON DELETE CASCADE,
  left_record_id uuid NOT NULL REFERENCES rural.registry_record(id) ON DELETE CASCADE,
  right_record_id uuid NOT NULL REFERENCES rural.registry_record(id) ON DELETE CASCADE,
  relationship text NOT NULL DEFAULT 'SAME_PHYSICAL_AREA_CANDIDATE',
  confidence numeric NOT NULL CHECK(confidence>=0 AND confidence<=1),
  status text NOT NULL DEFAULT 'CANDIDATE',
  reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(left_record_id<>right_record_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS rural_identity_link_pair_uidx ON rural.identity_link(asset_id,least(left_record_id,right_record_id),greatest(left_record_id,right_record_id),relationship);

-- Sensitive parties never require raw CPF/CNPJ. identifier_token is an HMAC/token produced
-- by an authorized connector; public APIs do not expose it.
CREATE TABLE IF NOT EXISTS rural.party_entity(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid,
  entity_type text NOT NULL CHECK(entity_type IN ('PERSON','ORGANIZATION','UNKNOWN')),
  display_name text,
  identifier_token text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rural_party_token_idx ON rural.party_entity(identifier_token) WHERE identifier_token IS NOT NULL;

CREATE TABLE IF NOT EXISTS rural.party_link(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid,
  party_id uuid NOT NULL REFERENCES rural.party_entity(id) ON DELETE CASCADE,
  registry_record_id uuid NOT NULL REFERENCES rural.registry_record(id) ON DELETE CASCADE,
  role text NOT NULL,
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  valid_from timestamptz,
  valid_to timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(party_id,registry_record_id,role,source_snapshot_id)
);

CREATE TABLE IF NOT EXISTS rural.monitor_checkpoint(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  monitor_id uuid NOT NULL REFERENCES rural.monitor(id) ON DELETE CASCADE,
  state_hash text NOT NULL,
  state jsonb NOT NULL,
  source_snapshot_ids uuid[] NOT NULL DEFAULT '{}',
  checked_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rural_monitor_checkpoint_idx ON rural.monitor_checkpoint(monitor_id,checked_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS rural_monitor_checkpoint_hash_uidx ON rural.monitor_checkpoint(monitor_id,state_hash);

CREATE TABLE IF NOT EXISTS rural.export_job(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  asset_id uuid NOT NULL REFERENCES rural.asset(id) ON DELETE CASCADE,
  format text NOT NULL CHECK(format IN ('KML','KMZ')),
  status text NOT NULL DEFAULT 'QUEUED',
  object_key text,
  sha256 text,
  size_bytes bigint,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS rural_export_job_idx ON rural.export_job(tenant_id,status,created_at DESC);

-- Records are visible through their asset. Shared official assets are readable; API writes are
-- limited in application code to tenant-owned assets.
ALTER TABLE rural.registry_record ENABLE ROW LEVEL SECURITY;
ALTER TABLE rural.registry_record FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rural_registry_record_visibility ON rural.registry_record;
CREATE POLICY rural_registry_record_visibility ON rural.registry_record FOR SELECT TO lotediretor_app USING (
  EXISTS (SELECT 1 FROM rural.asset a WHERE a.id=rural.registry_record.asset_id AND (a.tenant_id IS NULL OR a.tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid))
);
CREATE POLICY rural_registry_record_write ON rural.registry_record FOR ALL TO lotediretor_app USING (
  EXISTS (SELECT 1 FROM rural.asset a WHERE a.id=rural.registry_record.asset_id AND a.tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
) WITH CHECK (
  EXISTS (SELECT 1 FROM rural.asset a WHERE a.id=rural.registry_record.asset_id AND a.tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
);

DO $$ DECLARE item record; BEGIN
  FOR item IN SELECT * FROM (VALUES
    ('rural','monitor_checkpoint'),('rural','export_job')
  ) AS x(schemaname,tablename)
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',item.schemaname,item.tablename);
    EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',item.schemaname,item.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I.%I',item.schemaname,item.tablename);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I.%I FOR ALL TO lotediretor_app USING (tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid) WITH CHECK (tenant_id=nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',item.schemaname,item.tablename);
  END LOOP;
END $$;

ALTER TABLE rural.party_entity ENABLE ROW LEVEL SECURITY;
ALTER TABLE rural.party_entity FORCE ROW LEVEL SECURITY;
CREATE POLICY rural_party_visibility ON rural.party_entity FOR SELECT TO lotediretor_app USING (tenant_id IS NULL OR tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
CREATE POLICY rural_party_write ON rural.party_entity FOR ALL TO lotediretor_app USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
ALTER TABLE rural.party_link ENABLE ROW LEVEL SECURITY;
ALTER TABLE rural.party_link FORCE ROW LEVEL SECURITY;
CREATE POLICY rural_party_link_visibility ON rural.party_link FOR SELECT TO lotediretor_app USING (tenant_id IS NULL OR tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);
CREATE POLICY rural_party_link_write ON rural.party_link FOR ALL TO lotediretor_app USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid) WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);

-- Derived identity structures are visible only when their asset is visible.
ALTER TABLE rural.registry_identifier ENABLE ROW LEVEL SECURITY;
ALTER TABLE rural.registry_identifier FORCE ROW LEVEL SECURITY;
CREATE POLICY rural_identifier_visibility ON rural.registry_identifier FOR SELECT TO lotediretor_app USING (
 EXISTS(SELECT 1 FROM rural.asset a WHERE a.id=rural.registry_identifier.asset_id AND (a.tenant_id IS NULL OR a.tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid))
);
CREATE POLICY rural_identifier_write ON rural.registry_identifier FOR ALL TO lotediretor_app USING (
 EXISTS(SELECT 1 FROM rural.asset a WHERE a.id=rural.registry_identifier.asset_id AND a.tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
) WITH CHECK (
 EXISTS(SELECT 1 FROM rural.asset a WHERE a.id=rural.registry_identifier.asset_id AND a.tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
);
ALTER TABLE rural.geometry_version ENABLE ROW LEVEL SECURITY;
ALTER TABLE rural.geometry_version FORCE ROW LEVEL SECURITY;
CREATE POLICY rural_geometry_visibility ON rural.geometry_version FOR SELECT TO lotediretor_app USING (
 EXISTS(SELECT 1 FROM rural.asset a WHERE a.id=rural.geometry_version.asset_id AND (a.tenant_id IS NULL OR a.tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid))
);
CREATE POLICY rural_geometry_write ON rural.geometry_version FOR ALL TO lotediretor_app USING (
 EXISTS(SELECT 1 FROM rural.asset a WHERE a.id=rural.geometry_version.asset_id AND a.tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
) WITH CHECK (
 EXISTS(SELECT 1 FROM rural.asset a WHERE a.id=rural.geometry_version.asset_id AND a.tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
);
ALTER TABLE rural.identity_link ENABLE ROW LEVEL SECURITY;
ALTER TABLE rural.identity_link FORCE ROW LEVEL SECURITY;
CREATE POLICY rural_identity_visibility ON rural.identity_link FOR SELECT TO lotediretor_app USING (
 EXISTS(SELECT 1 FROM rural.asset a WHERE a.id=rural.identity_link.asset_id AND (a.tenant_id IS NULL OR a.tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid))
);
CREATE POLICY rural_identity_write ON rural.identity_link FOR ALL TO lotediretor_app USING (
 EXISTS(SELECT 1 FROM rural.asset a WHERE a.id=rural.identity_link.asset_id AND a.tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
) WITH CHECK (
 EXISTS(SELECT 1 FROM rural.asset a WHERE a.id=rural.identity_link.asset_id AND a.tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
);


ALTER TABLE rural.overlap_result ENABLE ROW LEVEL SECURITY;
ALTER TABLE rural.overlap_result FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rural_overlap_tenant ON rural.overlap_result;
CREATE POLICY rural_overlap_tenant ON rural.overlap_result FOR ALL TO lotediretor_app
USING (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK (tenant_id=nullif(current_setting('app.tenant_id',true),'')::uuid);

GRANT SELECT,INSERT,UPDATE,DELETE ON rural.registry_identifier,rural.geometry_version,rural.identity_link,rural.party_entity,rural.party_link,rural.monitor_checkpoint,rural.export_job TO lotediretor_app,lotediretor_worker;

INSERT INTO source.registry(code,title,authority,access_class,channel,base_url,data_owner,cadence,health,license_terms,provenance) VALUES
 ('SNCR','SNCR / CCIR','INCRA','C','authorized_integration','https://www.gov.br/incra/pt-br/assuntos/governanca-fundiaria/cadastro-imovel-rural','INCRA','on_demand','CONFIGURED','TERMS_REVIEW_REQUIRED','{"status":"CONFIGURED_NOT_INGESTED","does_not_prove_title":true}'::jsonb),
 ('CIB','CIB / CAFIR / CNIR','Receita Federal','C','authorized_integration','https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/programas-e-atividades/sinter/cib','Receita Federal','on_demand','CONFIGURED','TERMS_REVIEW_REQUIRED','{"status":"CONFIGURED_NOT_INGESTED","does_not_prove_title":true}'::jsonb),
 ('SICOR','SICOR / Crédito Rural e Proagro','Banco Central','A','official_download','https://www.bcb.gov.br/estabilidadefinanceira/tabelas-credito-rural-proagro','Banco Central','by_publication','CONFIGURED','OFFICIAL_TERMS_REVIEW_REQUIRED','{"status":"CONFIGURED_NOT_INGESTED","analytical_only":true}'::jsonb),
 ('FUNAI_TI','Terras Indígenas — geoprocessamento','FUNAI','A','official_geoservice','https://www.gov.br/funai/pt-br/atuacao/terras-indigenas/geoprocessamento-e-mapas','FUNAI','by_publication','CONFIGURED','OFFICIAL_TERMS_REVIEW_REQUIRED','{"status":"CONFIGURED_NOT_INGESTED"}'::jsonb),
 ('CNUC','Cadastro Nacional de Unidades de Conservação','MMA / ICMBio','A','official_download','https://www.gov.br/pt-br/servicos/obter-informacoes-sobre-as-unidades-de-conservacao-ambiental-nacionais','MMA / ICMBio','by_publication','CONFIGURED','OFFICIAL_TERMS_REVIEW_REQUIRED','{"status":"CONFIGURED_NOT_INGESTED"}'::jsonb)
ON CONFLICT(code) DO UPDATE SET title=excluded.title,authority=excluded.authority,access_class=excluded.access_class,channel=excluded.channel,base_url=excluded.base_url,data_owner=excluded.data_owner,cadence=excluded.cadence,provenance=source.registry.provenance||excluded.provenance;

INSERT INTO rural.layer_catalog(code,title,authority,legal_nature,status,metadata) VALUES
 ('SNCR','Sistema Nacional de Cadastro Rural / CCIR','INCRA','cadastral_rural','CONFIGURED','{"requires_authorized_source":true,"does_not_prove_title":true}'::jsonb),
 ('CIB','Cadastro Imobiliário Brasileiro / CAFIR','Receita Federal','fiscal_identifier','CONFIGURED','{"requires_authorized_source":true,"does_not_prove_title":true}'::jsonb),
 ('SICOR','Crédito Rural / Proagro','Banco Central','rural_credit','CONFIGURED','{"analytical_only":true,"does_not_prove_title":true}'::jsonb),
 ('FUNAI_TI','Terras Indígenas','FUNAI','territorial_restriction','CONFIGURED','{"requires_official_snapshot":true}'::jsonb),
 ('CNUC','Unidades de Conservação','MMA / ICMBio','protected_area','CONFIGURED','{"requires_official_snapshot":true}'::jsonb)
ON CONFLICT(code) DO UPDATE SET version=excluded.version,title=excluded.title,authority=excluded.authority,legal_nature=excluded.legal_nature,metadata=rural.layer_catalog.metadata||excluded.metadata;

INSERT INTO report.template(code,version,title,subject_types,section_order,status)
VALUES('RURAL360_360',1,'RE Rural 360 — Dossiê territorial e cadastral',ARRAY['rural_asset'],'["rural_cover","rural_identity","rural_registries","rural_convergence","rural_environment","rural_monitoring","rural_credit","rural_evidence","rural_limitations"]'::jsonb, 'ACTIVE')
ON CONFLICT(code) DO UPDATE SET version=excluded.version,title=excluded.title,subject_types=excluded.subject_types,section_order=excluded.section_order,status='ACTIVE';

UPDATE core.module SET status='V17_RURAL360' WHERE code='re-rural';
