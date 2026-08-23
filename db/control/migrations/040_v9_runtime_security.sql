-- v9: Control Plane runtime login role is separate from the migration owner.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lotediretor_control_app') THEN
    CREATE ROLE lotediretor_control_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
  END IF;
END $$;
GRANT CONNECT ON DATABASE lotediretor_control TO lotediretor_control_app;
GRANT USAGE ON SCHEMA tenant,catalog,billing,fiscal,cms,support,product,ops,release,admin,ai_ops TO lotediretor_control_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA tenant,catalog,billing,fiscal,cms,support,product,ops,release,admin,ai_ops TO lotediretor_control_app;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA tenant,catalog,billing,fiscal,cms,support,product,ops,release,admin,ai_ops TO lotediretor_control_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA tenant,catalog,billing,fiscal,cms,support,product,ops,release,admin,ai_ops GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO lotediretor_control_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA tenant,catalog,billing,fiscal,cms,support,product,ops,release,admin,ai_ops GRANT USAGE,SELECT ON SEQUENCES TO lotediretor_control_app;
