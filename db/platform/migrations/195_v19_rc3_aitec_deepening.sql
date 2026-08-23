-- v19-rc.3: A.I TEC branch/analysis/export persistence and tenant-consistent relationships.

CREATE UNIQUE INDEX IF NOT EXISTS aitec_project_tenant_id_uidx ON aitec.project(tenant_id,id);
CREATE UNIQUE INDEX IF NOT EXISTS aitec_constraint_snapshot_tenant_id_uidx ON aitec.constraint_snapshot(tenant_id,id);
CREATE UNIQUE INDEX IF NOT EXISTS aitec_solution_tenant_id_uidx ON aitec.solution(tenant_id,id);
CREATE UNIQUE INDEX IF NOT EXISTS aitec_geometry_object_tenant_id_uidx ON aitec.geometry_object(tenant_id,id);

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='aitec_solution_project_tenant_fk') THEN
    ALTER TABLE aitec.solution ADD CONSTRAINT aitec_solution_project_tenant_fk
      FOREIGN KEY(tenant_id,project_id) REFERENCES aitec.project(tenant_id,id) ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='aitec_solution_constraint_tenant_fk') THEN
    ALTER TABLE aitec.solution ADD CONSTRAINT aitec_solution_constraint_tenant_fk
      FOREIGN KEY(tenant_id,constraint_snapshot_id) REFERENCES aitec.constraint_snapshot(tenant_id,id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='aitec_solution_parent_tenant_fk') THEN
    ALTER TABLE aitec.solution ADD CONSTRAINT aitec_solution_parent_tenant_fk
      FOREIGN KEY(tenant_id,parent_solution_id) REFERENCES aitec.solution(tenant_id,id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='aitec_geometry_solution_tenant_fk') THEN
    ALTER TABLE aitec.geometry_object ADD CONSTRAINT aitec_geometry_solution_tenant_fk
      FOREIGN KEY(tenant_id,solution_id) REFERENCES aitec.solution(tenant_id,id) ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='aitec_violation_solution_tenant_fk') THEN
    ALTER TABLE aitec.violation ADD CONSTRAINT aitec_violation_solution_tenant_fk
      FOREIGN KEY(tenant_id,solution_id) REFERENCES aitec.solution(tenant_id,id) ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='aitec_lock_solution_tenant_fk') THEN
    ALTER TABLE aitec.solution_lock ADD CONSTRAINT aitec_lock_solution_tenant_fk
      FOREIGN KEY(tenant_id,solution_id) REFERENCES aitec.solution(tenant_id,id) ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='aitec_lock_geometry_tenant_fk') THEN
    ALTER TABLE aitec.solution_lock ADD CONSTRAINT aitec_lock_geometry_tenant_fk
      FOREIGN KEY(tenant_id,geometry_object_id) REFERENCES aitec.geometry_object(tenant_id,id) ON DELETE CASCADE;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS aitec.analysis_result(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  solution_id uuid NOT NULL,
  analysis_type text NOT NULL,
  method text NOT NULL,
  method_version text NOT NULL,
  input_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  output_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence_status text NOT NULL DEFAULT 'PRELIMINARY',
  source_snapshot_ids uuid[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(solution_id,analysis_type,method_version,created_at),
  CONSTRAINT aitec_analysis_solution_tenant_fk FOREIGN KEY(tenant_id,solution_id)
    REFERENCES aitec.solution(tenant_id,id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS aitec_analysis_solution_idx ON aitec.analysis_result(tenant_id,solution_id,analysis_type,created_at DESC);

ALTER TABLE aitec.artifact ALTER COLUMN scenario_id DROP NOT NULL;
ALTER TABLE aitec.artifact ADD COLUMN IF NOT EXISTS solution_id uuid;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='aitec_artifact_solution_fk') THEN
    ALTER TABLE aitec.artifact ADD CONSTRAINT aitec_artifact_solution_fk FOREIGN KEY(solution_id) REFERENCES aitec.solution(id) ON DELETE CASCADE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='aitec_artifact_one_owner_ck') THEN
    ALTER TABLE aitec.artifact ADD CONSTRAINT aitec_artifact_one_owner_ck CHECK (
      (CASE WHEN scenario_id IS NULL THEN 0 ELSE 1 END) + (CASE WHEN solution_id IS NULL THEN 0 ELSE 1 END) = 1
    );
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS aitec_artifact_solution_idx ON aitec.artifact(tenant_id,solution_id,created_at DESC) WHERE solution_id IS NOT NULL;

ALTER TABLE aitec.analysis_result ENABLE ROW LEVEL SECURITY;
ALTER TABLE aitec.analysis_result FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON aitec.analysis_result;
CREATE POLICY tenant_isolation ON aitec.analysis_result
USING (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid);

GRANT SELECT,INSERT,UPDATE,DELETE ON aitec.analysis_result TO lotediretor_app,lotediretor_worker;
