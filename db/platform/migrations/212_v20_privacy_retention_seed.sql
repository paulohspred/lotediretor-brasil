-- v20 privacy: keep retention defaults consistent for tenants created after migration 210.

CREATE OR REPLACE FUNCTION privacy.seed_default_retention_policies(p_tenant uuid) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,privacy AS $$
BEGIN
  INSERT INTO privacy.retention_policy(tenant_id,data_category,retention_days,expiry_action,legal_basis,automatic_execution,protected_class,owner,notes)
  VALUES
    (p_tenant,'AUDIT_TRAIL',1825,'RETAIN','legitimate_interest_and_compliance',false,true,'security','Append-only operational evidence; never deleted automatically.'),
    (p_tenant,'LEGAL_EVIDENCE',3650,'RETAIN','legal_claims_and_regulatory_evidence',false,true,'legal','Legal evidence requires explicit reviewed disposition.'),
    (p_tenant,'SOURCE_PROVENANCE',3650,'RETAIN','data_lineage_and_regulatory_evidence',false,true,'data-governance','Source hashes, snapshots and provenance must remain reproducible.'),
    (p_tenant,'IDENTITY_PROFILE',30,'ANONYMIZE','data_subject_erasure_or_end_of_relationship',false,false,'privacy','Request-driven only and blocked by active legal holds.')
  ON CONFLICT(tenant_id,data_category) DO NOTHING;
END $$;

CREATE OR REPLACE FUNCTION privacy.seed_default_retention_on_organization() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,privacy AS $$
BEGIN
  PERFORM privacy.seed_default_retention_policies(NEW.id);
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS organization_default_privacy_retention ON iam.organization;
CREATE TRIGGER organization_default_privacy_retention
AFTER INSERT ON iam.organization
FOR EACH ROW EXECUTE FUNCTION privacy.seed_default_retention_on_organization();

-- Backfill all current tenants, including SOURCE_PROVENANCE which migration 210
-- treated as protected in the API/guard model but did not seed explicitly.
DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT id FROM iam.organization LOOP
    PERFORM privacy.seed_default_retention_policies(r.id);
  END LOOP;
END $$;

GRANT EXECUTE ON FUNCTION privacy.seed_default_retention_policies(uuid) TO lotediretor_app;

COMMENT ON FUNCTION privacy.seed_default_retention_policies(uuid) IS 'Idempotent tenant privacy defaults. Protected audit/legal/provenance classes remain RETAIN/nonautomatic.';
