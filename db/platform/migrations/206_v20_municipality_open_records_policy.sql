-- v20: allow anonymous/public API reads only for records backed by the currently PUBLISHED snapshot of an OPEN ACTIVE dataset.
-- Tenant policies remain in force for all other access.

DROP POLICY IF EXISTS open_ctm_read ON municipality.ctm_parcel;
CREATE POLICY open_ctm_read ON municipality.ctm_parcel FOR SELECT USING (
  source_snapshot_id IS NOT NULL AND EXISTS(
    SELECT 1 FROM municipality.dataset d
    JOIN municipality.dataset_snapshot s ON s.dataset_id=d.id AND s.status='PUBLISHED'
    WHERE d.municipality_tenant_id=ctm_parcel.municipality_tenant_id
      AND d.kind='CTM' AND d.visibility='OPEN' AND d.status='ACTIVE'
      AND s.source_snapshot_id=ctm_parcel.source_snapshot_id
  )
);

DROP POLICY IF EXISTS open_pgv_read ON municipality.pgv_value;
CREATE POLICY open_pgv_read ON municipality.pgv_value FOR SELECT USING (
  source_snapshot_id IS NOT NULL AND EXISTS(
    SELECT 1 FROM municipality.dataset d
    JOIN municipality.dataset_snapshot s ON s.dataset_id=d.id AND s.status='PUBLISHED'
    WHERE d.municipality_tenant_id=pgv_value.municipality_tenant_id
      AND d.kind='PGV' AND d.visibility='OPEN' AND d.status='ACTIVE'
      AND s.source_snapshot_id=pgv_value.source_snapshot_id
  )
);

DROP POLICY IF EXISTS open_iptu_read ON municipality.iptu_record;
CREATE POLICY open_iptu_read ON municipality.iptu_record FOR SELECT USING (
  source_snapshot_id IS NOT NULL AND EXISTS(
    SELECT 1 FROM municipality.dataset d
    JOIN municipality.dataset_snapshot s ON s.dataset_id=d.id AND s.status='PUBLISHED'
    WHERE d.municipality_tenant_id=iptu_record.municipality_tenant_id
      AND d.kind='IPTU' AND d.visibility='OPEN' AND d.status='ACTIVE'
      AND s.source_snapshot_id=iptu_record.source_snapshot_id
  )
);

DROP POLICY IF EXISTS open_itbi_read ON municipality.itbi_record;
CREATE POLICY open_itbi_read ON municipality.itbi_record FOR SELECT USING (
  source_snapshot_id IS NOT NULL AND EXISTS(
    SELECT 1 FROM municipality.dataset d
    JOIN municipality.dataset_snapshot s ON s.dataset_id=d.id AND s.status='PUBLISHED'
    WHERE d.municipality_tenant_id=itbi_record.municipality_tenant_id
      AND d.kind='ITBI' AND d.visibility='OPEN' AND d.status='ACTIVE'
      AND s.source_snapshot_id=itbi_record.source_snapshot_id
  )
);
