-- v9: production runtime role + enforced tenant isolation.
-- The login password is assigned by ops/db/bootstrap-runtime-roles.sh, never committed here.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lotediretor_app') THEN
    CREATE ROLE lotediretor_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lotediretor_tiles') THEN
    CREATE ROLE lotediretor_tiles NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END $$;

GRANT CONNECT ON DATABASE lotediretor TO lotediretor_app, lotediretor_tiles;
GRANT USAGE ON SCHEMA iam,core,source,geo,legal,planning,evidence,cadastre,registry,rural,infra,market,property360,crm,condo,municipality,solar,aitec,analysis,report,notification,ingest,data_quality TO lotediretor_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA iam,core,source,geo,legal,planning,evidence,cadastre,registry,rural,infra,market,property360,crm,condo,municipality,solar,aitec,analysis,report,notification,ingest,data_quality TO lotediretor_app;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA iam,core,source,geo,legal,planning,evidence,cadastre,registry,rural,infra,market,property360,crm,condo,municipality,solar,aitec,analysis,report,notification,ingest,data_quality TO lotediretor_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA iam,core,source,geo,legal,planning,evidence,cadastre,registry,rural,infra,market,property360,crm,condo,municipality,solar,aitec,analysis,report,notification,ingest,data_quality GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO lotediretor_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA iam,core,source,geo,legal,planning,evidence,cadastre,registry,rural,infra,market,property360,crm,condo,municipality,solar,aitec,analysis,report,notification,ingest,data_quality GRANT USAGE,SELECT ON SEQUENCES TO lotediretor_app;

GRANT USAGE ON SCHEMA tiles TO lotediretor_tiles;
GRANT SELECT ON ALL TABLES IN SCHEMA tiles TO lotediretor_tiles;
ALTER DEFAULT PRIVILEGES IN SCHEMA tiles GRANT SELECT ON TABLES TO lotediretor_tiles;

DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT schemaname,tablename FROM pg_tables
    WHERE schemaname IN ('property360','crm','rural','condo','municipality','solar','aitec','analysis','report','notification','ingest')
      AND EXISTS (
        SELECT 1 FROM information_schema.columns c
        WHERE c.table_schema=schemaname AND c.table_name=tablename AND c.column_name='tenant_id'
      )
  LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',r.schemaname,r.tablename);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I.%I',r.schemaname,r.tablename);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I.%I FOR ALL TO lotediretor_app USING (tenant_id = nullif(current_setting(''app.tenant_id'', true),'''')::uuid) WITH CHECK (tenant_id = nullif(current_setting(''app.tenant_id'', true),'''')::uuid)',
      r.schemaname,r.tablename
    );
  END LOOP;
END $$;
