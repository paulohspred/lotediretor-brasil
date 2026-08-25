-- v20: harden legacy municipality tables created before the Prefeitura control plane.
-- Every tenant-owned municipal record must be isolated by app.tenant_id, including legacy CTM/IPTU/doc review tables.

DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT * FROM (VALUES
    ('document'),('rule_review'),('ctm_parcel'),('iptu_record')
  ) AS x(tablename)
  LOOP
    EXECUTE format('ALTER TABLE municipality.%I ENABLE ROW LEVEL SECURITY',r.tablename);
    EXECUTE format('ALTER TABLE municipality.%I FORCE ROW LEVEL SECURITY',r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON municipality.%I',r.tablename);
    EXECUTE format($p$CREATE POLICY tenant_isolation ON municipality.%I USING (
      EXISTS(SELECT 1 FROM municipality.tenant mt WHERE mt.id=municipality.%I.municipality_tenant_id AND mt.organization_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
    ) WITH CHECK (
      EXISTS(SELECT 1 FROM municipality.tenant mt WHERE mt.id=municipality.%I.municipality_tenant_id AND mt.organization_id=nullif(current_setting('app.tenant_id',true),'')::uuid)
    )$p$,r.tablename,r.tablename,r.tablename);
  END LOOP;
END $$;

GRANT SELECT,INSERT,UPDATE,DELETE ON municipality.document,municipality.rule_review,municipality.ctm_parcel,municipality.iptu_record TO lotediretor_app,lotediretor_worker;
