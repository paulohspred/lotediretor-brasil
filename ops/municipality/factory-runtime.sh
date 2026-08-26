#!/usr/bin/env bash
set -euo pipefail
: "${PLATFORM_DB_MIGRATION_USER:=lotediretor}" "${PLATFORM_DB_MIGRATION_PASSWORD:=lotediretor_local}" "${PLATFORM_DB_NAME:=lotediretor}" "${PLATFORM_DB_APP_USER:=lotediretor_app}" "${PLATFORM_DB_APP_PASSWORD:=change-me-app}"

OWNER_SQL=/tmp/ld-factory-owner.sql
cat > "$OWNER_SQL" <<'SQL'
BEGIN;
INSERT INTO iam.organization(id,name,kind,status) VALUES
 ('0198f209-0000-7000-8000-000000000001','Factory Runtime A','MUNICIPALITY','ACTIVE'),
 ('0198f209-0000-7000-8000-000000000002','Factory Runtime B','MUNICIPALITY','ACTIVE') ON CONFLICT(id) DO NOTHING;
INSERT INTO core.municipality(ibge_code,name,uf) VALUES('3550308','São Paulo','SP'),('3304557','Rio de Janeiro','RJ') ON CONFLICT(ibge_code) DO NOTHING;
INSERT INTO municipality.tenant(id,organization_id,municipality_ibge,status) VALUES
 ('0198f209-1000-7000-8000-000000000001','0198f209-0000-7000-8000-000000000001','3550308','ACTIVE'),
 ('0198f209-1000-7000-8000-000000000002','0198f209-0000-7000-8000-000000000002','3304557','ACTIVE') ON CONFLICT(id) DO NOTHING;
INSERT INTO source.registry(id,code,authority,access_class,channel,license_terms,health) VALUES
 ('0198f209-2000-7000-8000-000000000001','MF_RUNTIME_A','Runtime Official A','A','WFS','runtime synthetic','UP'),
 ('0198f209-2000-7000-8000-000000000002','MF_RUNTIME_B','Runtime Official B','A','WFS','runtime synthetic','UP') ON CONFLICT(id) DO NOTHING;
INSERT INTO municipality.factory_source(id,municipality_tenant_id,municipality_ibge,dataset_code,source_id,contract_id,adapter,endpoint_url,pinned_config,connector_status,homologation_status,license_status,created_by)
SELECT '0198f209-3000-7000-8000-000000000001','0198f209-1000-7000-8000-000000000001','3550308','RUNTIME_A','0198f209-2000-7000-8000-000000000001',c.id,'WFS','https://example.invalid/geoserver/ows','{"typeName":"runtime:lote","srsName":"EPSG:4326"}'::jsonb,'CANDIDATE','UNREVIEWED','UNVERIFIED','runtime'
FROM source.connector_contract c WHERE c.code='WFS_GIS' AND c.version=1
ON CONFLICT(id) DO NOTHING;
INSERT INTO municipality.factory_source(id,municipality_tenant_id,municipality_ibge,dataset_code,source_id,contract_id,adapter,endpoint_url,pinned_config,connector_status,homologation_status,license_status,created_by)
SELECT '0198f209-3000-7000-8000-000000000002','0198f209-1000-7000-8000-000000000002','3304557','RUNTIME_B','0198f209-2000-7000-8000-000000000002',c.id,'WFS','https://example.invalid/geoserver/ows','{"typeName":"runtime:lote","srsName":"EPSG:4326"}'::jsonb,'CANDIDATE','UNREVIEWED','UNVERIFIED','runtime'
FROM source.connector_contract c WHERE c.code='WFS_GIS' AND c.version=1
ON CONFLICT(id) DO NOTHING;
DO $$ BEGIN
  BEGIN
    UPDATE municipality.factory_source SET connector_status='ACTIVE' WHERE id='0198f209-3000-7000-8000-000000000001';
    RAISE EXCEPTION 'factory activation without license/discovery unexpectedly succeeded';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM='factory activation without license/discovery unexpectedly succeeded' THEN RAISE; END IF;
    IF position('factory_activation_requires_verified_license' in SQLERRM)=0 THEN RAISE; END IF;
  END;
END $$;
COMMIT;
SELECT municipality.refresh_factory_coverage_snapshot();
SQL
cat "$OWNER_SQL" | docker compose exec -T -e PGPASSWORD="$PLATFORM_DB_MIGRATION_PASSWORD" platform-db psql -h 127.0.0.1 -U "$PLATFORM_DB_MIGRATION_USER" -d "$PLATFORM_DB_NAME" -v ON_ERROR_STOP=1

APP_SQL=/tmp/ld-factory-app.sql
cat > "$APP_SQL" <<'SQL'
BEGIN;
SELECT set_config('app.tenant_id','0198f209-0000-7000-8000-000000000001',true);
DO $$ DECLARE n integer; BEGIN
  SELECT count(*) INTO n FROM municipality.factory_source WHERE id IN ('0198f209-3000-7000-8000-000000000001','0198f209-3000-7000-8000-000000000002');
  IF n<>1 THEN RAISE EXCEPTION 'factory runtime RLS read isolation failed: % rows',n; END IF;
  IF EXISTS(SELECT 1 FROM municipality.factory_source WHERE id='0198f209-3000-7000-8000-000000000002') THEN RAISE EXCEPTION 'factory foreign tenant row visible'; END IF;
  BEGIN
    INSERT INTO municipality.factory_monitor_event(municipality_tenant_id,factory_source_id,change_kind,severity)
    VALUES('0198f209-1000-7000-8000-000000000002','0198f209-3000-7000-8000-000000000002','UNCHANGED','INFO');
    RAISE EXCEPTION 'factory cross tenant write unexpectedly succeeded';
  EXCEPTION WHEN insufficient_privilege THEN NULL; WHEN check_violation THEN NULL;
  END;
END $$;
ROLLBACK;
SQL
cat "$APP_SQL" | docker compose exec -T -e PGPASSWORD="$PLATFORM_DB_APP_PASSWORD" platform-db psql -h 127.0.0.1 -U "$PLATFORM_DB_APP_USER" -d "$PLATFORM_DB_NAME" -v ON_ERROR_STOP=1

echo 'Municipality Factory runtime DB guards + RLS PASS'
