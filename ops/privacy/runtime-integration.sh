#!/usr/bin/env bash
set -euo pipefail
: "${PLATFORM_DB_MIGRATION_USER:=lotediretor}" "${PLATFORM_DB_MIGRATION_PASSWORD:=lotediretor_local}" "${PLATFORM_DB_NAME:=lotediretor}" "${PLATFORM_DB_APP_USER:=lotediretor_app}" "${PLATFORM_DB_APP_PASSWORD:=change-me-app}"

OWNER_SQL=/tmp/ld-privacy-seed.sql
cat > "$OWNER_SQL" <<'SQL'
BEGIN;
INSERT INTO iam.organization(id,name,kind,status) VALUES
 ('0198f209-0000-7000-8000-000000000001','Privacy Runtime A','COMPANY','ACTIVE'),
 ('0198f209-0000-7000-8000-000000000002','Privacy Runtime B','COMPANY','ACTIVE'),
 ('0198f209-0000-7000-8000-000000000003','Privacy Runtime Provisioning','COMPANY','ACTIVE') ON CONFLICT(id) DO NOTHING;
DO $$ DECLARE n integer; BEGIN
  SELECT count(*) INTO n FROM privacy.retention_policy
  WHERE tenant_id='0198f209-0000-7000-8000-000000000003'
    AND data_category IN ('AUDIT_TRAIL','LEGAL_EVIDENCE','SOURCE_PROVENANCE','IDENTITY_PROFILE');
  IF n<>4 THEN RAISE EXCEPTION 'new tenant default retention provisioning expected 4 rows, got %',n; END IF;
END $$;
INSERT INTO iam.user_profile(id,email,display_name) VALUES
 ('0198f209-1000-7000-8000-000000000001','privacy-a@example.invalid','Privacy A'),
 ('0198f209-1000-7000-8000-000000000002','privacy-b@example.invalid','Privacy B')
ON CONFLICT(id) DO UPDATE SET email=excluded.email,display_name=excluded.display_name,privacy_status='ACTIVE',anonymized_at=null;
INSERT INTO iam.membership(organization_id,user_id,role) VALUES
 ('0198f209-0000-7000-8000-000000000001','0198f209-1000-7000-8000-000000000001','admin'),
 ('0198f209-0000-7000-8000-000000000002','0198f209-1000-7000-8000-000000000002','admin')
ON CONFLICT(organization_id,user_id) DO UPDATE SET role=excluded.role;
-- Persistent foreign fixture used only to prove tenant A cannot see tenant B.
INSERT INTO privacy.subject_request(id,tenant_id,subject_user_id,request_type,status,request_reason,requested_by)
VALUES('0198f209-2000-7000-8000-000000000002','0198f209-0000-7000-8000-000000000002','0198f209-1000-7000-8000-000000000002','ACCESS','REQUESTED','foreign tenant fixture','0198f209-1000-7000-8000-000000000002')
ON CONFLICT(id) DO NOTHING;
COMMIT;
SQL
cat "$OWNER_SQL" | docker compose exec -T -e PGPASSWORD="$PLATFORM_DB_MIGRATION_PASSWORD" platform-db psql -h 127.0.0.1 -U "$PLATFORM_DB_MIGRATION_USER" -d "$PLATFORM_DB_NAME" -v ON_ERROR_STOP=1

APP_SQL=/tmp/ld-privacy-app.sql
cat > "$APP_SQL" <<'SQL'
BEGIN;
SELECT set_config('app.tenant_id','0198f209-0000-7000-8000-000000000001',true);
INSERT INTO privacy.subject_request(id,tenant_id,subject_user_id,request_type,status,request_reason,requested_by)
VALUES('0198f209-2000-7000-8000-000000000001','0198f209-0000-7000-8000-000000000001','0198f209-1000-7000-8000-000000000001','ERASURE','REQUESTED','runtime proof','0198f209-1000-7000-8000-000000000001');

DO $$ DECLARE n integer; BEGIN
  SELECT count(*) INTO n FROM privacy.subject_request;
  IF n<>1 THEN RAISE EXCEPTION 'privacy RLS expected 1 visible request, got %',n; END IF;
  BEGIN
    INSERT INTO privacy.subject_request(id,tenant_id,subject_user_id,request_type,status,requested_by)
    VALUES('0198f209-2000-7000-8000-000000000003','0198f209-0000-7000-8000-000000000002','0198f209-1000-7000-8000-000000000002','ACCESS','REQUESTED','0198f209-1000-7000-8000-000000000001');
    RAISE EXCEPTION 'privacy cross-tenant insert unexpectedly succeeded';
  EXCEPTION WHEN insufficient_privilege THEN NULL; WHEN check_violation THEN NULL;
  END;
END $$;

UPDATE privacy.subject_request SET status='IDENTITY_VERIFIED',verified_at=now(),reviewed_by='0198f209-1000-7000-8000-000000000001' WHERE id='0198f209-2000-7000-8000-000000000001';
UPDATE privacy.subject_request SET status='APPROVED',decided_at=now(),reviewed_by='0198f209-1000-7000-8000-000000000001' WHERE id='0198f209-2000-7000-8000-000000000001';
INSERT INTO privacy.legal_hold(id,tenant_id,subject_user_id,data_category,reason,legal_basis,created_by)
VALUES('0198f209-3000-7000-8000-000000000001','0198f209-0000-7000-8000-000000000001','0198f209-1000-7000-8000-000000000001','IDENTITY','runtime hold','test legal basis','0198f209-1000-7000-8000-000000000001');
DO $$ BEGIN
  BEGIN
    UPDATE privacy.subject_request SET status='EXECUTING' WHERE id='0198f209-2000-7000-8000-000000000001';
    RAISE EXCEPTION 'erasure entered EXECUTING despite active hold';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM NOT LIKE '%privacy_erasure_blocked_by_legal_hold%' THEN RAISE; END IF;
  END;
END $$;
UPDATE privacy.legal_hold SET active=false,released_by='0198f209-1000-7000-8000-000000000001',released_at=now(),release_reason='runtime release' WHERE id='0198f209-3000-7000-8000-000000000001';
UPDATE privacy.subject_request SET status='EXECUTING' WHERE id='0198f209-2000-7000-8000-000000000001';

INSERT INTO privacy.operation_event(id,tenant_id,subject_user_id,request_id,action,actor_id)
VALUES('0198f209-4000-7000-8000-000000000001','0198f209-0000-7000-8000-000000000001','0198f209-1000-7000-8000-000000000001','0198f209-2000-7000-8000-000000000001','RUNTIME_PROOF','0198f209-1000-7000-8000-000000000001');
DO $$ BEGIN
  BEGIN
    UPDATE privacy.operation_event SET action='MUTATED' WHERE id='0198f209-4000-7000-8000-000000000001';
    RAISE EXCEPTION 'append-only privacy event mutated';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM NOT LIKE '%privacy_operation_event_is_append_only%' THEN RAISE; END IF;
  END;
END $$;

INSERT INTO privacy.retention_policy(tenant_id,data_category,retention_days,expiry_action,legal_basis,automatic_execution,protected_class,owner)
VALUES('0198f209-0000-7000-8000-000000000001','AUDIT_TRAIL',365,'RETAIN','runtime basis',false,true,'runtime')
ON CONFLICT(tenant_id,data_category) DO UPDATE SET retention_days=excluded.retention_days,expiry_action='RETAIN',legal_basis=excluded.legal_basis,automatic_execution=false,protected_class=true,owner=excluded.owner;
DO $$ BEGIN
  BEGIN
    UPDATE privacy.retention_policy SET expiry_action='DELETE',protected_class=false WHERE tenant_id='0198f209-0000-7000-8000-000000000001' AND data_category='AUDIT_TRAIL';
    RAISE EXCEPTION 'protected retention class became destructive';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM NOT LIKE '%privacy_protected_class_must_be_retain_nonautomatic%' THEN RAISE; END IF;
  END;
END $$;
ROLLBACK;
SQL
cat "$APP_SQL" | docker compose exec -T -e PGPASSWORD="$PLATFORM_DB_APP_PASSWORD" platform-db psql -h 127.0.0.1 -U "$PLATFORM_DB_APP_USER" -d "$PLATFORM_DB_NAME" -v ON_ERROR_STOP=1

echo 'Privacy/LGPD runtime RLS + provisioning + hold + append-only + retention guards PASS'
