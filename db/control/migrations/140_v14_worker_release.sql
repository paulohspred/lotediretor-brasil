DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lotediretor_control_worker') THEN
    CREATE ROLE lotediretor_control_worker NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END $$;
GRANT CONNECT ON DATABASE lotediretor_control TO lotediretor_control_worker;
GRANT USAGE ON SCHEMA tenant,catalog,billing,fiscal,cms,support,product,ops,release,admin,ai_ops TO lotediretor_control_worker;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA tenant,catalog,billing,fiscal,cms,support,product,ops,release,admin,ai_ops TO lotediretor_control_worker;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA tenant,catalog,billing,fiscal,cms,support,product,ops,release,admin,ai_ops TO lotediretor_control_worker;

UPDATE release.release SET status='INACTIVE' WHERE environment='local' AND status='ACTIVE' AND version<>'14.0.0';
INSERT INTO release.release(version,environment,status) VALUES('14.0.0','local','ACTIVE')
ON CONFLICT(version,environment) DO UPDATE SET status='ACTIVE';
