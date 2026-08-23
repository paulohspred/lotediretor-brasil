-- v20: deterministic legal/rule graph foundation aligned with Blueprint Final v2.0.
-- This migration does not confirm municipal rules. It only provides the structures
-- required to represent temporal legal effects, deterministic dependencies and
-- explicit bindings without collapsing unknown/conflicting law into a false answer.

ALTER TABLE legal.relation ADD COLUMN IF NOT EXISTS source_article_id uuid REFERENCES legal.article(id);
ALTER TABLE legal.relation ADD COLUMN IF NOT EXISTS target_article_id uuid REFERENCES legal.article(id);
ALTER TABLE legal.relation ADD COLUMN IF NOT EXISTS valid_from timestamptz;
ALTER TABLE legal.relation ADD COLUMN IF NOT EXISTS valid_to timestamptz;
ALTER TABLE legal.relation ADD COLUMN IF NOT EXISTS recorded_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE legal.relation ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'CANDIDATE';
ALTER TABLE legal.relation ADD COLUMN IF NOT EXISTS review_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS legal_relation_from_type_idx
  ON legal.relation(from_document_version_id,relation_type,status,valid_from,valid_to);
CREATE INDEX IF NOT EXISTS legal_relation_to_type_idx
  ON legal.relation(to_document_version_id,relation_type,status,valid_from,valid_to);
CREATE INDEX IF NOT EXISTS legal_relation_source_article_idx ON legal.relation(source_article_id);
CREATE INDEX IF NOT EXISTS legal_relation_target_article_idx ON legal.relation(target_article_id);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname='legal_relation_type_v20_check' AND conrelid='legal.relation'::regclass
  ) THEN
    ALTER TABLE legal.relation ADD CONSTRAINT legal_relation_type_v20_check CHECK (
      relation_type IN (
        'ALTERA','REVOGA','REGULAMENTA','CONSOLIDA','SUSPENDE_EFICACIA',
        'RESTAURA_EFICACIA','CORRIGE','REFERENCIA','SUBSTITUI','OTHER'
      )
    ) NOT VALID;
  END IF;
END $$;

ALTER TABLE legal.rule ADD COLUMN IF NOT EXISTS rule_code text;
ALTER TABLE legal.rule ADD COLUMN IF NOT EXISTS rule_family text;
ALTER TABLE legal.rule ADD COLUMN IF NOT EXISTS legal_effect text NOT NULL DEFAULT 'COMPUTATIONAL';
ALTER TABLE legal.rule ADD COLUMN IF NOT EXISTS hard_constraint boolean NOT NULL DEFAULT false;
ALTER TABLE legal.rule ADD COLUMN IF NOT EXISTS priority integer NOT NULL DEFAULT 100;
ALTER TABLE legal.rule ADD COLUMN IF NOT EXISTS formula jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE legal.rule ADD COLUMN IF NOT EXISTS input_schema jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE legal.rule ADD COLUMN IF NOT EXISTS output_schema jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE legal.rule ADD COLUMN IF NOT EXISTS confirmed_by text;
ALTER TABLE legal.rule ADD COLUMN IF NOT EXISTS confirmed_at timestamptz;
ALTER TABLE legal.rule ADD COLUMN IF NOT EXISTS superseded_by_rule_id uuid REFERENCES legal.rule(id);

CREATE INDEX IF NOT EXISTS legal_rule_code_idx
  ON legal.rule(municipality_ibge,rule_code,status,valid_from,valid_to)
  WHERE rule_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS legal_rule_family_idx
  ON legal.rule(municipality_ibge,rule_family,status,valid_from,valid_to)
  WHERE rule_family IS NOT NULL;
CREATE INDEX IF NOT EXISTS legal_rule_formula_gin ON legal.rule USING gin(formula);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname='legal_rule_effect_v20_check' AND conrelid='legal.rule'::regclass
  ) THEN
    ALTER TABLE legal.rule ADD CONSTRAINT legal_rule_effect_v20_check CHECK (
      legal_effect IN ('PERMISSIVE','RESTRICTIVE','COMPUTATIONAL','PROCEDURAL','INFORMATIONAL')
    ) NOT VALID;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS legal.rule_dependency(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  rule_id uuid NOT NULL REFERENCES legal.rule(id) ON DELETE CASCADE,
  depends_on_rule_id uuid NOT NULL REFERENCES legal.rule(id) ON DELETE CASCADE,
  dependency_type text NOT NULL DEFAULT 'REQUIRES',
  condition jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'CANDIDATE',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(rule_id<>depends_on_rule_id),
  CHECK(dependency_type IN ('REQUIRES','OVERRIDES','LIMITS','EXCLUDES','DERIVES_FROM')),
  UNIQUE(rule_id,depends_on_rule_id,dependency_type)
);
CREATE INDEX IF NOT EXISTS legal_rule_dependency_reverse_idx
  ON legal.rule_dependency(depends_on_rule_id,dependency_type,status);

-- Generic binding layer. Municipal specifics such as outorga, CEPAC, TDC,
-- ZEIS/HIS/HMP, EIV/PGT, heritage, aerodrome, easement and road-widening
-- remain explicit subjects backed by confirmed legal.rule rows.
CREATE TABLE IF NOT EXISTS planning.rule_binding(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  rule_id uuid NOT NULL REFERENCES legal.rule(id) ON DELETE CASCADE,
  municipality_ibge text NOT NULL,
  zone_code text,
  use_code text,
  binding_type text NOT NULL,
  subject_code text NOT NULL,
  hard_constraint boolean NOT NULL DEFAULT false,
  condition jsonb NOT NULL DEFAULT '{}'::jsonb,
  valid_from timestamptz,
  valid_to timestamptz,
  status text NOT NULL DEFAULT 'CANDIDATE',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(binding_type IN ('PARAMETER','USE','INSTRUMENT','LICENSING_TRIGGER','SPATIAL_RESTRICTION','CALCULATION')),
  CHECK(status IN ('CANDIDATE','CONFIRMED','REJECTED','SUPERSEDED'))
);
CREATE INDEX IF NOT EXISTS planning_rule_binding_lookup_idx
  ON planning.rule_binding(municipality_ibge,zone_code,use_code,binding_type,subject_code,status,valid_from,valid_to);
CREATE INDEX IF NOT EXISTS planning_rule_binding_condition_gin ON planning.rule_binding USING gin(condition);

GRANT SELECT ON legal.rule_dependency,planning.rule_binding TO lotediretor_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON legal.rule_dependency,planning.rule_binding TO lotediretor_worker;
