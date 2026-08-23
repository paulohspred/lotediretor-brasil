CREATE TABLE IF NOT EXISTS core.municipality(
  ibge_code text PRIMARY KEY,
  name text NOT NULL,
  uf text NOT NULL,
  region text,
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE source.registry ADD COLUMN IF NOT EXISTS title text;
ALTER TABLE source.registry ADD COLUMN IF NOT EXISTS base_url text;
ALTER TABLE source.registry ADD COLUMN IF NOT EXISTS data_owner text;
ALTER TABLE source.registry ADD COLUMN IF NOT EXISTS provenance jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE source.snapshot ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'INGESTED';
ALTER TABLE source.snapshot ADD COLUMN IF NOT EXISTS quality jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE source.snapshot ADD COLUMN IF NOT EXISTS published_at timestamptz;

CREATE TABLE IF NOT EXISTS source.publication(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  source_id uuid NOT NULL REFERENCES source.registry(id),
  municipality_ibge text,
  snapshot_id uuid NOT NULL REFERENCES source.snapshot(id),
  status text NOT NULL DEFAULT 'ACTIVE',
  activated_at timestamptz NOT NULL DEFAULT now(),
  deactivated_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS source_publication_active_uq
  ON source.publication(source_id, COALESCE(municipality_ibge,'')) WHERE status='ACTIVE';

CREATE TABLE IF NOT EXISTS planning.analysis_parameter(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  run_id uuid NOT NULL REFERENCES analysis.run(id) ON DELETE CASCADE,
  parameter text NOT NULL,
  value_numeric numeric,
  value_text text,
  unit text,
  status text NOT NULL,
  rule_id uuid REFERENCES legal.rule(id),
  source_document_version_id uuid REFERENCES legal.document_version(id),
  source_locator text,
  created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO source.registry(code,title,authority,access_class,channel,base_url,data_owner,cadence,health,provenance)
VALUES(
  'IBGE_LOCALIDADES',
  'IBGE Localidades — Municípios',
  'Instituto Brasileiro de Geografia e Estatística',
  'A',
  'REST',
  'https://servicodados.ibge.gov.br/api/v1/localidades/municipios',
  'IBGE',
  'ON_DEMAND',
  'UNKNOWN',
  '{"official":true,"purpose":"municipality_catalog"}'::jsonb
)
ON CONFLICT(code) DO UPDATE SET
  title=excluded.title,
  authority=excluded.authority,
  base_url=excluded.base_url,
  data_owner=excluded.data_owner,
  provenance=excluded.provenance;

UPDATE core.module SET status='V2_CORE_READY' WHERE code='imovel360';
