-- v19-rc.1: geometry-aware A.I TEC site-solver persistence.
-- Keeps generated alternatives reproducible and separates solution objects/violations/locks
-- instead of hiding geometry only inside a JSON metrics blob.

CREATE TABLE IF NOT EXISTS aitec.solution(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL REFERENCES aitec.project(id) ON DELETE CASCADE,
  constraint_snapshot_id uuid REFERENCES aitec.constraint_snapshot(id) ON DELETE SET NULL,
  parent_solution_id uuid REFERENCES aitec.solution(id) ON DELETE SET NULL,
  solver_version text NOT NULL,
  seed bigint NOT NULL,
  variation_index int NOT NULL,
  status text NOT NULL DEFAULT 'GENERATED',
  objectives jsonb NOT NULL DEFAULT '{}'::jsonb,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation jsonb NOT NULL DEFAULT '{}'::jsonb,
  assumptions jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_pareto boolean NOT NULL DEFAULT false,
  pareto_rank int,
  generated_at timestamptz NOT NULL DEFAULT now(),
  approved_by text,
  approved_at timestamptz,
  UNIQUE(project_id,solver_version,seed,variation_index)
);
CREATE INDEX IF NOT EXISTS aitec_solution_project_idx ON aitec.solution(tenant_id,project_id,generated_at DESC);
CREATE INDEX IF NOT EXISTS aitec_solution_pareto_idx ON aitec.solution(tenant_id,project_id,is_pareto,pareto_rank) WHERE is_pareto;

CREATE TABLE IF NOT EXISTS aitec.geometry_object(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  solution_id uuid NOT NULL REFERENCES aitec.solution(id) ON DELETE CASCADE,
  object_type text NOT NULL,
  ordinal int NOT NULL DEFAULT 0,
  geom geometry(Geometry,4326) NOT NULL,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  lineage jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(solution_id,object_type,ordinal)
);
CREATE INDEX IF NOT EXISTS aitec_geometry_object_solution_idx ON aitec.geometry_object(tenant_id,solution_id,object_type,ordinal);
CREATE INDEX IF NOT EXISTS aitec_geometry_object_geom_gix ON aitec.geometry_object USING gist(geom);

CREATE TABLE IF NOT EXISTS aitec.violation(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  solution_id uuid NOT NULL REFERENCES aitec.solution(id) ON DELETE CASCADE,
  constraint_code text NOT NULL,
  status text NOT NULL,
  severity text NOT NULL DEFAULT 'HARD',
  observed jsonb NOT NULL DEFAULT '{}'::jsonb,
  expected jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  explanation text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS aitec_violation_solution_idx ON aitec.violation(tenant_id,solution_id,status,severity);

CREATE TABLE IF NOT EXISTS aitec.solution_lock(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  solution_id uuid NOT NULL REFERENCES aitec.solution(id) ON DELETE CASCADE,
  geometry_object_id uuid REFERENCES aitec.geometry_object(id) ON DELETE CASCADE,
  lock_code text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(solution_id,geometry_object_id,lock_code)
);
CREATE INDEX IF NOT EXISTS aitec_solution_lock_idx ON aitec.solution_lock(tenant_id,solution_id);

DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT schemaname,tablename FROM pg_tables WHERE (schemaname,tablename) IN (
    ('aitec','solution'),('aitec','geometry_object'),('aitec','violation'),('aitec','solution_lock')
  ) LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I.%I',r.schemaname,r.tablename);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I.%I USING (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'',true),'''')::uuid)',r.schemaname,r.tablename);
  END LOOP;
END $$;
