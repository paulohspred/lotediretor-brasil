-- v20: durable asynchronous A.I TEC execution queue.
-- The queue persists the exact solver inputs/context and never grants the solver
-- authority to change tenant/project ownership supplied by the authenticated API.

CREATE TABLE IF NOT EXISTS aitec.job(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  constraint_snapshot_id uuid,
  operation text NOT NULL,
  args jsonb NOT NULL DEFAULT '[]'::jsonb CHECK(jsonb_typeof(args)='array'),
  kwargs jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(kwargs)='object'),
  execution_context jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(execution_context)='object'),
  status text NOT NULL DEFAULT 'QUEUED' CHECK(status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED')),
  attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),
  solver_version text,
  classification text,
  professional_review_required boolean,
  engine_response jsonb,
  error text,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  CONSTRAINT aitec_job_project_tenant_fk FOREIGN KEY(tenant_id,project_id)
    REFERENCES aitec.project(tenant_id,id) ON DELETE CASCADE,
  CONSTRAINT aitec_job_constraint_tenant_fk FOREIGN KEY(tenant_id,constraint_snapshot_id)
    REFERENCES aitec.constraint_snapshot(tenant_id,id)
);
CREATE INDEX IF NOT EXISTS aitec_job_tenant_status_idx ON aitec.job(tenant_id,status,created_at DESC);
CREATE INDEX IF NOT EXISTS aitec_job_queue_idx ON aitec.job(status,created_at) WHERE status='QUEUED';
CREATE INDEX IF NOT EXISTS aitec_job_project_idx ON aitec.job(tenant_id,project_id,created_at DESC);

ALTER TABLE aitec.job ENABLE ROW LEVEL SECURITY;
ALTER TABLE aitec.job FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON aitec.job;
CREATE POLICY tenant_isolation ON aitec.job
USING (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid)
WITH CHECK (tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid);

GRANT SELECT,INSERT,UPDATE,DELETE ON aitec.job TO lotediretor_app,lotediretor_worker;
