#!/usr/bin/env bash
set -euo pipefail
: "${PLATFORM_DB_MIGRATION_USER:=lotediretor}" "${PLATFORM_DB_MIGRATION_PASSWORD:=lotediretor_local}" "${PLATFORM_DB_NAME:=lotediretor}" "${PLATFORM_DB_APP_USER:=lotediretor_app}" "${PLATFORM_DB_APP_PASSWORD:=change-me-app}"
OWNER_SQL=/tmp/ld-rls-seed.sql
cat > "$OWNER_SQL" <<'SQL'
BEGIN;
INSERT INTO iam.organization(id,name,kind,status) VALUES
 ('0198f009-0000-7000-8000-000000000001','RLS Runtime A','COMPANY','ACTIVE'),
 ('0198f009-0000-7000-8000-000000000002','RLS Runtime B','COMPANY','ACTIVE') ON CONFLICT(id) DO NOTHING;
INSERT INTO property360.property(id,tenant_id,name) VALUES
 ('0198f009-1000-7000-8000-000000000001','0198f009-0000-7000-8000-000000000001','Runtime tenant A'),
 ('0198f009-1000-7000-8000-000000000002','0198f009-0000-7000-8000-000000000002','Runtime tenant B')
ON CONFLICT(id) DO UPDATE SET tenant_id=excluded.tenant_id,name=excluded.name;
COMMIT;
SQL
cat "$OWNER_SQL" | docker compose exec -T -e PGPASSWORD="$PLATFORM_DB_MIGRATION_PASSWORD" platform-db psql -h 127.0.0.1 -U "$PLATFORM_DB_MIGRATION_USER" -d "$PLATFORM_DB_NAME" -v ON_ERROR_STOP=1
APP_SQL=/tmp/ld-rls-app.sql
cat > "$APP_SQL" <<'SQL'
BEGIN;
SELECT set_config('app.tenant_id','0198f009-0000-7000-8000-000000000001',true);
DO $$ DECLARE n integer; BEGIN
 SELECT count(*) INTO n FROM property360.property WHERE id IN ('0198f009-1000-7000-8000-000000000001','0198f009-1000-7000-8000-000000000002');
 IF n <> 1 THEN RAISE EXCEPTION 'runtime RLS read isolation failed: % rows',n; END IF;
 IF EXISTS(SELECT 1 FROM property360.property WHERE id='0198f009-1000-7000-8000-000000000002') THEN RAISE EXCEPTION 'foreign tenant row visible'; END IF;
 BEGIN
   INSERT INTO property360.property(id,tenant_id,name) VALUES('0198f009-1000-7000-8000-000000000003','0198f009-0000-7000-8000-000000000002','must fail');
   RAISE EXCEPTION 'cross tenant write unexpectedly succeeded';
 EXCEPTION WHEN insufficient_privilege THEN NULL; WHEN check_violation THEN NULL;
 END;
END $$;
ROLLBACK;
SQL
cat "$APP_SQL" | docker compose exec -T -e PGPASSWORD="$PLATFORM_DB_APP_PASSWORD" platform-db psql -h 127.0.0.1 -U "$PLATFORM_DB_APP_USER" -d "$PLATFORM_DB_NAME" -v ON_ERROR_STOP=1
echo 'Runtime non-owner RLS isolation PASS'
