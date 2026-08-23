\set ON_ERROR_STOP on
BEGIN;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lotediretor_rls_test') THEN
    CREATE ROLE lotediretor_rls_test NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END $$;
GRANT USAGE ON SCHEMA property360,analysis,report,notification,condo,solar,aitec TO lotediretor_rls_test;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA property360,analysis,report,notification,condo,solar,aitec TO lotediretor_rls_test;

-- Stable test tenants. Data is rolled back at the end.
INSERT INTO iam.organization(id,name,kind,status) VALUES
 ('0198f008-0000-7000-8000-000000000001','RLS Test A','COMPANY','ACTIVE'),
 ('0198f008-0000-7000-8000-000000000002','RLS Test B','COMPANY','ACTIVE')
ON CONFLICT(id) DO NOTHING;
INSERT INTO property360.property(id,tenant_id,name) VALUES
 ('0198f008-1000-7000-8000-000000000001','0198f008-0000-7000-8000-000000000001','Tenant A marker'),
 ('0198f008-1000-7000-8000-000000000002','0198f008-0000-7000-8000-000000000002','Tenant B marker')
ON CONFLICT(id) DO UPDATE SET tenant_id=excluded.tenant_id,name=excluded.name;

SET LOCAL ROLE lotediretor_rls_test;
SELECT set_config('app.tenant_id','0198f008-0000-7000-8000-000000000001',true);
DO $$
DECLARE n integer;
BEGIN
  SELECT count(*) INTO n FROM property360.property WHERE id IN ('0198f008-1000-7000-8000-000000000001','0198f008-1000-7000-8000-000000000002');
  IF n <> 1 THEN RAISE EXCEPTION 'RLS isolation failed: tenant A can see % marker rows', n; END IF;
  IF NOT EXISTS (SELECT 1 FROM property360.property WHERE id='0198f008-1000-7000-8000-000000000001') THEN
    RAISE EXCEPTION 'RLS isolation failed: own row is not visible';
  END IF;
  IF EXISTS (SELECT 1 FROM property360.property WHERE id='0198f008-1000-7000-8000-000000000002') THEN
    RAISE EXCEPTION 'RLS isolation failed: foreign row visible';
  END IF;
END $$;

DO $$
BEGIN
  BEGIN
    INSERT INTO property360.property(id,tenant_id,name) VALUES('0198f008-1000-7000-8000-000000000003','0198f008-0000-7000-8000-000000000002','must fail');
    RAISE EXCEPTION 'RLS WITH CHECK failed: cross-tenant insert unexpectedly succeeded';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
END $$;
RESET ROLE;
ROLLBACK;
\echo 'RLS tenant isolation PASS'
