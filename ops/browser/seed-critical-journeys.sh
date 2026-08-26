#!/usr/bin/env bash
set -euo pipefail
: "${PLATFORM_DB_MIGRATION_USER:=lotediretor}"
: "${PLATFORM_DB_MIGRATION_PASSWORD:=lotediretor_local}"
: "${PLATFORM_DB_NAME:=lotediretor}"

cat >/tmp/ld-browser-critical-fixtures.sql <<'SQL'
BEGIN;

INSERT INTO core.municipality(ibge_code,name,uf,region)
VALUES('3550308','São Paulo','SP','Sudeste')
ON CONFLICT(ibge_code) DO UPDATE SET name=excluded.name,uf=excluded.uf,region=excluded.region,updated_at=now();

INSERT INTO source.registry(id,code,title,authority,access_class,channel,base_url,data_owner,cadence,health,provenance,license_terms)
VALUES(
 '0198f230-0000-7000-8000-000000000001','BROWSER_CRITICAL_FIXTURE','Critical browser journey synthetic fixture','LoteDiretor test fixture','A','FIXTURE','fixture://browser-critical','LoteDiretor','ON_DEMAND','OK',
 '{"synthetic":true,"purpose":"browser_critical_e2e","must_never_be_promoted_as_official":true}'::jsonb,
 'Synthetic fixture for automated testing only; not an official or licensed municipal dataset.'
)
ON CONFLICT(code) DO UPDATE SET title=excluded.title,health='OK',provenance=excluded.provenance,license_terms=excluded.license_terms;

INSERT INTO source.snapshot(id,source_id,source_date,parser_version,sha256,metadata,status,quality,published_at,record_count,validation_status,schema_version)
SELECT
 '0198f230-1000-7000-8000-000000000001',id,'2026-08-26T00:00:00Z','browser-critical-v20',repeat('c',64),
 '{"synthetic":true,"fixture":"critical-browser-journeys"}'::jsonb,'VALIDATED','{"fixture":true}'::jsonb,now(),1,'PASS','browser-critical-v20'
FROM source.registry WHERE code='BROWSER_CRITICAL_FIXTURE'
ON CONFLICT(id) DO UPDATE SET validation_status='PASS',status='VALIDATED',published_at=now(),metadata=excluded.metadata;

INSERT INTO source.publication(id,source_id,municipality_ibge,dataset_code,snapshot_id,status,activated_at)
SELECT '0198f230-2000-7000-8000-000000000001',r.id,'3550308','BROWSER_CRITICAL_FIXTURE',s.id,'ACTIVE',now()
FROM source.registry r JOIN source.snapshot s ON s.source_id=r.id AND s.id='0198f230-1000-7000-8000-000000000001'
WHERE r.code='BROWSER_CRITICAL_FIXTURE'
ON CONFLICT(id) DO UPDATE SET snapshot_id=excluded.snapshot_id,status='ACTIVE',deactivated_at=null;

INSERT INTO geo.parcel(id,tenant_id,municipality_ibge,source_snapshot_id,official_identifier,geom,valid_from,recorded_at,superseded_at)
VALUES(
 '0198f230-3000-7000-8000-000000000001',NULL,'3550308','0198f230-1000-7000-8000-000000000001','E2E-SP-CRITICAL-001',
 ST_Multi(ST_GeomFromText('POLYGON((-46.63345 -23.55065,-46.63315 -23.55065,-46.63315 -23.55035,-46.63345 -23.55035,-46.63345 -23.55065))',4326)),
 '2020-01-01T00:00:00Z',now(),NULL
)
ON CONFLICT(id) DO UPDATE SET geom=excluded.geom,source_snapshot_id=excluded.source_snapshot_id,valid_from=excluded.valid_from,superseded_at=NULL,recorded_at=now();

INSERT INTO geo.municipality_boundary(municipality_ibge,source_snapshot_id,geom,valid_from,recorded_at)
VALUES(
 '3550308','0198f230-1000-7000-8000-000000000001',
 ST_Multi(ST_GeomFromText('POLYGON((-46.64 -23.56,-46.62 -23.56,-46.62 -23.54,-46.64 -23.54,-46.64 -23.56))',4326)),
 '2020-01-01T00:00:00Z',now()
)
ON CONFLICT(municipality_ibge,source_snapshot_id) DO UPDATE SET geom=excluded.geom,valid_from=excluded.valid_from,valid_to=NULL,recorded_at=now();

INSERT INTO planning.zone(id,municipality_ibge,code,name,geom,source_snapshot_id,valid_from,valid_to)
VALUES(
 '0198f230-4000-7000-8000-000000000001','3550308','E2E-ZONE','Zona sintética E2E',
 ST_Multi(ST_GeomFromText('POLYGON((-46.634 -23.551,-46.633 -23.551,-46.633 -23.55,-46.634 -23.55,-46.634 -23.551))',4326)),
 '0198f230-1000-7000-8000-000000000001','2020-01-01T00:00:00Z',NULL
)
ON CONFLICT DO NOTHING;
UPDATE planning.zone SET geom=ST_Multi(ST_GeomFromText('POLYGON((-46.634 -23.551,-46.633 -23.551,-46.633 -23.55,-46.634 -23.55,-46.634 -23.551))',4326)),source_snapshot_id='0198f230-1000-7000-8000-000000000001',valid_to=NULL
WHERE id='0198f230-4000-7000-8000-000000000001';

-- Ensure a current local entitlement exists without replacing billing-derived
-- snapshots in non-local environments. This fixture targets only LOCAL_ORG.
UPDATE core.entitlement_snapshot SET valid_to=now()
WHERE organization_id='0198f001-0000-7000-8000-000000000001' AND valid_to IS NULL;
INSERT INTO core.entitlement_snapshot(organization_id,snapshot,valid_from)
VALUES('0198f001-0000-7000-8000-000000000001',
 '{"tier":"browser-critical-local","modules":["imovel360","re-rural","condominio","energia-solar","ai-tec","prefeitura","relatorios"],"quotas":{}}'::jsonb,now());

COMMIT;
SQL

cat /tmp/ld-browser-critical-fixtures.sql | docker compose exec -T \
  -e PGPASSWORD="$PLATFORM_DB_MIGRATION_PASSWORD" platform-db \
  psql -h 127.0.0.1 -U "$PLATFORM_DB_MIGRATION_USER" -d "$PLATFORM_DB_NAME" -v ON_ERROR_STOP=1

echo 'Critical browser journey fixtures PASS (synthetic/non-official)'
