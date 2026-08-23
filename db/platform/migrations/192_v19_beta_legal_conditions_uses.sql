-- v19-beta: separate executable rule conditions from extraction provenance and add explicit use permissions.
ALTER TABLE legal.rule ADD COLUMN IF NOT EXISTS extraction_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE legal.rule ADD COLUMN IF NOT EXISTS source_article_id uuid REFERENCES legal.article(id);
CREATE INDEX IF NOT EXISTS legal_rule_article_idx ON legal.rule(source_article_id);
CREATE INDEX IF NOT EXISTS legal_rule_condition_gin ON legal.rule USING gin(condition);

-- v19-alpha stored deterministic parser provenance in condition. Move only pure
-- legacy metadata objects; do not rewrite any operator-bearing legal condition.
UPDATE legal.rule
SET extraction_metadata = extraction_metadata || condition,
    condition = '{}'::jsonb
WHERE condition ? 'extractor'
  AND (condition - ARRAY['extractor','excerpt','offset','article_path']) = '{}'::jsonb;

CREATE TABLE IF NOT EXISTS planning.zone_use_permission(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_ibge text NOT NULL,
  zone_code text NOT NULL,
  use_code text NOT NULL,
  use_name text,
  permission text NOT NULL CHECK(permission IN ('PERMITTED','CONDITIONED','SPECIAL','TOLERATED','NONCONFORMING','PROHIBITED','UNKNOWN')),
  condition jsonb NOT NULL DEFAULT '{}'::jsonb,
  valid_from timestamptz,
  valid_to timestamptz,
  source_document_version_id uuid REFERENCES legal.document_version(id),
  source_article_id uuid REFERENCES legal.article(id),
  source_locator text,
  status text NOT NULL DEFAULT 'CANDIDATE' CHECK(status IN ('CANDIDATE','CONFIRMED','REJECTED','SUPERSEDED')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS zone_use_permission_lookup_idx ON planning.zone_use_permission(municipality_ibge,zone_code,use_code,status,valid_from,valid_to);
CREATE INDEX IF NOT EXISTS zone_use_permission_condition_gin ON planning.zone_use_permission USING gin(condition);
