-- v20: public open-data read policy and municipality tenant reassignment guard.

CREATE OR REPLACE FUNCTION municipality.prevent_tenant_reassignment()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.organization_id IS DISTINCT FROM NEW.organization_id THEN
    RAISE EXCEPTION 'municipality_tenant_organization_is_immutable';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS municipality_tenant_no_reassignment ON municipality.tenant;
CREATE TRIGGER municipality_tenant_no_reassignment BEFORE UPDATE OF organization_id ON municipality.tenant FOR EACH ROW EXECUTE FUNCTION municipality.prevent_tenant_reassignment();

CREATE UNIQUE INDEX IF NOT EXISTS municipality_member_role_null_department_uq
  ON municipality.member_role(municipality_tenant_id,subject_id,role,COALESCE(department_id,'00000000-0000-0000-0000-000000000000'::uuid));

DROP POLICY IF EXISTS open_dataset_read ON municipality.dataset;
CREATE POLICY open_dataset_read ON municipality.dataset FOR SELECT
  USING (visibility='OPEN' AND status='ACTIVE');

DROP POLICY IF EXISTS open_dataset_snapshot_read ON municipality.dataset_snapshot;
CREATE POLICY open_dataset_snapshot_read ON municipality.dataset_snapshot FOR SELECT
  USING (status='PUBLISHED' AND EXISTS(
    SELECT 1 FROM municipality.dataset d WHERE d.id=dataset_snapshot.dataset_id AND d.visibility='OPEN' AND d.status='ACTIVE'
  ));
