-- v20: materialized municipal export snapshots required before offboarding.
ALTER TABLE municipality.export_job ADD COLUMN IF NOT EXISTS materialized_at timestamptz;
ALTER TABLE municipality.export_job ADD COLUMN IF NOT EXISTS record_count bigint NOT NULL DEFAULT 0;
ALTER TABLE municipality.export_job ADD COLUMN IF NOT EXISTS bundle_sha256 text;

CREATE TABLE IF NOT EXISTS municipality.export_chunk(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  municipality_tenant_id uuid NOT NULL REFERENCES municipality.tenant(id) ON DELETE CASCADE,
  export_job_id uuid NOT NULL REFERENCES municipality.export_job(id) ON DELETE CASCADE,
  dataset_name text NOT NULL,
  ordinal integer NOT NULL CHECK(ordinal>=0),
  row_count integer NOT NULL CHECK(row_count>=0),
  payload jsonb NOT NULL,
  sha256 text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(export_job_id,dataset_name,ordinal)
);
ALTER TABLE municipality.export_chunk ENABLE ROW LEVEL SECURITY;
ALTER TABLE municipality.export_chunk FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON municipality.export_chunk;
CREATE POLICY tenant_isolation ON municipality.export_chunk USING (
  EXISTS(SELECT 1 FROM municipality.tenant mt WHERE mt.id=municipality.export_chunk.municipality_tenant_id AND mt.organization_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
) WITH CHECK (
  EXISTS(SELECT 1 FROM municipality.tenant mt WHERE mt.id=municipality.export_chunk.municipality_tenant_id AND mt.organization_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
);
CREATE INDEX IF NOT EXISTS municipality_export_chunk_idx ON municipality.export_chunk(export_job_id,dataset_name,ordinal);
GRANT SELECT,INSERT,UPDATE,DELETE ON municipality.export_chunk TO lotediretor_app,lotediretor_worker;

CREATE OR REPLACE FUNCTION municipality.require_materialized_export_for_offboarding()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE e municipality.export_job%ROWTYPE;
BEGIN
  SELECT * INTO e FROM municipality.export_job WHERE id=NEW.export_job_id AND municipality_tenant_id=NEW.municipality_tenant_id;
  IF e.id IS NULL OR e.status<>'READY' OR e.materialized_at IS NULL OR (e.expires_at IS NOT NULL AND e.expires_at<=now()) THEN
    RAISE EXCEPTION 'materialized_ready_export_required_before_offboarding';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS municipality_offboarding_export_guard ON municipality.offboarding_case;
CREATE TRIGGER municipality_offboarding_export_guard BEFORE INSERT OR UPDATE OF export_job_id ON municipality.offboarding_case FOR EACH ROW EXECUTE FUNCTION municipality.require_materialized_export_for_offboarding();
