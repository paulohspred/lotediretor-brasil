#!/usr/bin/env bash
set -euo pipefail
: "${PLATFORM_DB_MIGRATION_USER:=lotediretor}" "${PLATFORM_DB_MIGRATION_PASSWORD:=lotediretor_local}" "${PLATFORM_DB_NAME:=lotediretor}" "${PLATFORM_DB_APP_USER:=lotediretor_app}" "${PLATFORM_DB_APP_PASSWORD:=change-me-app}"
: "${CONTROL_DB_MIGRATION_USER:=lotediretor_control}" "${CONTROL_DB_MIGRATION_PASSWORD:=lotediretor_control_local}" "${CONTROL_DB_NAME:=lotediretor_control}" "${CONTROL_DB_APP_USER:=lotediretor_control_app}" "${CONTROL_DB_APP_PASSWORD:=change-me-control-app}"

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
INSERT INTO aitec.project(id,tenant_id,name,status) VALUES
 ('0198f009-2000-7000-8000-000000000001','0198f009-0000-7000-8000-000000000001','A.I TEC tenant A','DRAFT'),
 ('0198f009-2000-7000-8000-000000000002','0198f009-0000-7000-8000-000000000002','A.I TEC tenant B','DRAFT')
ON CONFLICT(id) DO UPDATE SET tenant_id=excluded.tenant_id,name=excluded.name,status=excluded.status;
INSERT INTO aitec.job(id,tenant_id,project_id,operation,args,kwargs,execution_context,status,created_by) VALUES
 ('0198f009-3000-7000-8000-000000000001','0198f009-0000-7000-8000-000000000001','0198f009-2000-7000-8000-000000000001','terrain.tin','[]','{}','{"tenant_id":"0198f009-0000-7000-8000-000000000001","project_id":"0198f009-2000-7000-8000-000000000001"}','QUEUED','rls-seed'),
 ('0198f009-3000-7000-8000-000000000002','0198f009-0000-7000-8000-000000000002','0198f009-2000-7000-8000-000000000002','terrain.tin','[]','{}','{"tenant_id":"0198f009-0000-7000-8000-000000000002","project_id":"0198f009-2000-7000-8000-000000000002"}','QUEUED','rls-seed')
ON CONFLICT(id) DO UPDATE SET tenant_id=excluded.tenant_id,project_id=excluded.project_id,status='QUEUED';
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

 SELECT count(*) INTO n FROM aitec.job WHERE id IN ('0198f009-3000-7000-8000-000000000001','0198f009-3000-7000-8000-000000000002');
 IF n <> 1 THEN RAISE EXCEPTION 'A.I TEC job RLS read isolation failed: % rows',n; END IF;
 IF EXISTS(SELECT 1 FROM aitec.job WHERE id='0198f009-3000-7000-8000-000000000002') THEN RAISE EXCEPTION 'foreign A.I TEC job visible'; END IF;
 BEGIN
   INSERT INTO aitec.job(id,tenant_id,project_id,operation,args,kwargs,execution_context,status,created_by)
   VALUES('0198f009-3000-7000-8000-000000000003','0198f009-0000-7000-8000-000000000002','0198f009-2000-7000-8000-000000000002','terrain.tin','[]','{}','{}','QUEUED','must-fail');
   RAISE EXCEPTION 'cross tenant A.I TEC job write unexpectedly succeeded';
 EXCEPTION WHEN insufficient_privilege THEN NULL; WHEN check_violation THEN NULL;
 END;
END $$;
ROLLBACK;
SQL
cat "$APP_SQL" | docker compose exec -T -e PGPASSWORD="$PLATFORM_DB_APP_PASSWORD" platform-db psql -h 127.0.0.1 -U "$PLATFORM_DB_APP_USER" -d "$PLATFORM_DB_NAME" -v ON_ERROR_STOP=1

CONTROL_OWNER_SQL=/tmp/ld-control-rls-seed.sql
cat > "$CONTROL_OWNER_SQL" <<'SQL'
BEGIN;
INSERT INTO tenant.tenant(id,name,kind,status) VALUES
 ('0198f109-0000-7000-8000-000000000001','Control RLS A','COMPANY','ACTIVE'),
 ('0198f109-0000-7000-8000-000000000002','Control RLS B','COMPANY','ACTIVE') ON CONFLICT(id) DO NOTHING;
INSERT INTO support.customer_success_account(tenant_id,health,lifecycle_stage,updated_by) VALUES
 ('0198f109-0000-7000-8000-000000000001','HEALTHY','ACTIVE','runtime-seed'),
 ('0198f109-0000-7000-8000-000000000002','AT_RISK','ACTIVE','runtime-seed')
ON CONFLICT(tenant_id) DO UPDATE SET health=excluded.health,lifecycle_stage=excluded.lifecycle_stage,updated_by=excluded.updated_by,updated_at=now();
COMMIT;
SQL
cat "$CONTROL_OWNER_SQL" | docker compose exec -T -e PGPASSWORD="$CONTROL_DB_MIGRATION_PASSWORD" control-db psql -h 127.0.0.1 -U "$CONTROL_DB_MIGRATION_USER" -d "$CONTROL_DB_NAME" -v ON_ERROR_STOP=1

CONTROL_APP_SQL=/tmp/ld-control-rls-app.sql
cat > "$CONTROL_APP_SQL" <<'SQL'
BEGIN;
SELECT set_config('app.tenant_id','0198f109-0000-7000-8000-000000000001',true);
DO $$ DECLARE n integer; BEGIN
 SELECT count(*) INTO n FROM support.customer_success_account WHERE tenant_id IN ('0198f109-0000-7000-8000-000000000001','0198f109-0000-7000-8000-000000000002');
 IF n <> 1 THEN RAISE EXCEPTION 'control runtime RLS read isolation failed: % rows',n; END IF;
 IF EXISTS(SELECT 1 FROM support.customer_success_account WHERE tenant_id='0198f109-0000-7000-8000-000000000002') THEN RAISE EXCEPTION 'control foreign tenant row visible'; END IF;
 BEGIN
   INSERT INTO support.customer_success_account(tenant_id,health,lifecycle_stage,updated_by) VALUES('0198f109-0000-7000-8000-000000000002','HEALTHY','ACTIVE','must-fail');
   RAISE EXCEPTION 'control cross tenant write unexpectedly succeeded';
 EXCEPTION WHEN insufficient_privilege THEN NULL; WHEN check_violation THEN NULL;
 END;
END $$;
ROLLBACK;
SQL
cat "$CONTROL_APP_SQL" | docker compose exec -T -e PGPASSWORD="$CONTROL_DB_APP_PASSWORD" control-db psql -h 127.0.0.1 -U "$CONTROL_DB_APP_USER" -d "$CONTROL_DB_NAME" -v ON_ERROR_STOP=1

echo 'Runtime non-owner RLS isolation PASS (platform + A.I TEC job + control)'
