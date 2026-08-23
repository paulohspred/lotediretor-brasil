CREATE SCHEMA IF NOT EXISTS report;
CREATE SCHEMA IF NOT EXISTS notification;

CREATE TABLE IF NOT EXISTS property360.comparable(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid,
  municipality_ibge text NOT NULL,
  neighborhood text,
  property_type text,
  area_m2 numeric NOT NULL CHECK(area_m2 > 0),
  price_cents bigint NOT NULL CHECK(price_cents > 0),
  latitude double precision,
  longitude double precision,
  source_kind text NOT NULL DEFAULT 'DEMO',
  source_snapshot_id uuid REFERENCES source.snapshot(id),
  observed_at date,
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS property360_comparable_lookup_idx ON property360.comparable(municipality_ibge,property_type,observed_at DESC);

CREATE TABLE IF NOT EXISTS property360.avm_run(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  property_id uuid REFERENCES property360.property(id),
  municipality_ibge text NOT NULL,
  area_m2 numeric NOT NULL CHECK(area_m2 > 0),
  model_version text NOT NULL,
  status text NOT NULL DEFAULT 'CALCULATED',
  estimate_cents bigint,
  confidence numeric,
  comparable_ids uuid[] NOT NULL DEFAULT '{}',
  assumptions jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS report.report_run(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  kind text NOT NULL,
  subject_type text NOT NULL,
  subject_id text NOT NULL,
  base_date date,
  status text NOT NULL DEFAULT 'QUEUED',
  input_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  artifact_key text,
  sha256 text,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS notification.notification(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  user_id text,
  kind text NOT NULL,
  title text NOT NULL,
  body text,
  status text NOT NULL DEFAULT 'UNREAD',
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  read_at timestamptz
);

INSERT INTO property360.comparable(municipality_ibge,neighborhood,property_type,area_m2,price_cents,source_kind,observed_at,attributes)
SELECT * FROM (VALUES
  ('3550308','Centro','APARTMENT',62::numeric,62000000::bigint,'DEMO',current_date-30,'{"label":"Comparável demonstrativo 1"}'::jsonb),
  ('3550308','Centro','APARTMENT',78::numeric,78000000::bigint,'DEMO',current_date-20,'{"label":"Comparável demonstrativo 2"}'::jsonb),
  ('3550308','Centro','APARTMENT',95::numeric,95000000::bigint,'DEMO',current_date-10,'{"label":"Comparável demonstrativo 3"}'::jsonb)
) AS v(municipality_ibge,neighborhood,property_type,area_m2,price_cents,source_kind,observed_at,attributes)
WHERE NOT EXISTS (SELECT 1 FROM property360.comparable WHERE source_kind='DEMO');

UPDATE core.module SET status='V3_OPERATIONAL' WHERE code IN ('imovel360','relatorios');
