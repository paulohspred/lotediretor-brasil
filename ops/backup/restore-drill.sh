#!/usr/bin/env bash
set -euo pipefail

SRC="${1:?usage: ops/backup/restore-drill.sh backups/<timestamp>}"
PLATFORM_OWNER="${PLATFORM_DB_MIGRATION_USER:-lotediretor}"
CONTROL_OWNER="${CONTROL_DB_MIGRATION_USER:-lotediretor_control}"
ENVIRONMENT="${DEPLOY_ENVIRONMENT:-${NODE_ENV:-local}}"
STAMP="$(basename "$SRC")"
START_EPOCH=$(date +%s)
DR_ARTIFACT_DIR="${DR_ARTIFACT_DIR:-runtime-artifacts/dr}"
mkdir -p "$DR_ARTIFACT_DIR"

test -f "$SRC/platform.dump" && test -f "$SRC/control.dump" && test -f "$SRC/METADATA.txt" && test -f "$SRC/SHA256SUMS.txt"
( cd "$SRC" && sha256sum -c SHA256SUMS.txt )

metadata_value(){ awk -F= -v key="$1" '$1==key{print substr($0,index($0,"=")+1);exit}' "$SRC/METADATA.txt"; }
BACKUP_START_EPOCH="$(metadata_value backup_started_epoch)"
BACKUP_COMPLETED_EPOCH="$(metadata_value backup_completed_epoch)"
if [[ ! "$BACKUP_START_EPOCH" =~ ^[0-9]+$ || ! "$BACKUP_COMPLETED_EPOCH" =~ ^[0-9]+$ || "$BACKUP_COMPLETED_EPOCH" -lt "$BACKUP_START_EPOCH" ]]; then
  echo "invalid backup capture timestamps in METADATA.txt" >&2
  exit 1
fi
# The local drill simulates failure immediately after the backup capture completes.
# This makes the capture window a conservative synthetic RPO. Production RPO must
# be measured from the real failure timestamp and the last durable restore point.
SIMULATED_FAILURE_EPOCH="${DR_SIMULATED_FAILURE_EPOCH:-$BACKUP_COMPLETED_EPOCH}"
if [[ ! "$SIMULATED_FAILURE_EPOCH" =~ ^[0-9]+$ || "$SIMULATED_FAILURE_EPOCH" -lt "$BACKUP_START_EPOCH" ]]; then
  echo "invalid DR_SIMULATED_FAILURE_EPOCH" >&2
  exit 1
fi
RPO_SECONDS=$((SIMULATED_FAILURE_EPOCH-BACKUP_START_EPOCH))

PDB="ld_restore_platform_$$"
CDB="ld_restore_control_$$"
TMP_OBJECT_DIR=$(mktemp -d)
DRILL_BUCKET=$(printf 'ld-restore-%s-%s' "${STAMP:0:18}" "$$" | tr '[:upper:]_' '[:lower:]-' | sed -E 's/[^a-z0-9.-]+/-/g' | cut -c1-63)
cleanup(){
  docker compose exec -T platform-db psql -U "$PLATFORM_OWNER" -d postgres -c "DROP DATABASE IF EXISTS $PDB WITH (FORCE)" >/dev/null 2>&1 || true
  docker compose exec -T control-db psql -U "$CONTROL_OWNER" -d postgres -c "DROP DATABASE IF EXISTS $CDB WITH (FORCE)" >/dev/null 2>&1 || true
  docker compose run --rm --no-deps --entrypoint /bin/sh minio-init -c \
    "mc alias set local http://minio:9000 '${S3_ACCESS_KEY:-lotediretor}' '${S3_SECRET_KEY:-lotediretor-local-secret}' >/dev/null 2>&1 && mc rm --recursive --force local/'$DRILL_BUCKET' >/dev/null 2>&1 || true; mc rb --force local/'$DRILL_BUCKET' >/dev/null 2>&1 || true" >/dev/null 2>&1 || true
  rm -rf "$TMP_OBJECT_DIR"
}
trap cleanup EXIT
cleanup

docker compose exec -T platform-db createdb -U "$PLATFORM_OWNER" "$PDB"
docker compose exec -T control-db createdb -U "$CONTROL_OWNER" "$CDB"
cat "$SRC/platform.dump" | docker compose exec -T platform-db pg_restore -U "$PLATFORM_OWNER" -d "$PDB" --no-owner --no-acl
cat "$SRC/control.dump" | docker compose exec -T control-db pg_restore -U "$CONTROL_OWNER" -d "$CDB" --no-owner --no-acl

# Validate representative critical contracts after restore and raise on any
# missing relation. A boolean SELECT that merely prints false is not a gate.
docker compose exec -T platform-db psql -v ON_ERROR_STOP=1 -U "$PLATFORM_OWNER" -d "$PDB" <<'SQL' >/dev/null
DO $$
DECLARE migrations integer;
BEGIN
  SELECT count(*) INTO migrations FROM public.schema_migrations;
  IF migrations <= 0 THEN RAISE EXCEPTION 'platform schema_migrations empty after restore'; END IF;
  IF to_regclass('iam.organization') IS NULL THEN RAISE EXCEPTION 'iam.organization missing after restore'; END IF;
  IF to_regclass('aitec.job') IS NULL THEN RAISE EXCEPTION 'aitec.job missing after restore'; END IF;
  IF to_regclass('report.report_run') IS NULL THEN RAISE EXCEPTION 'report.report_run missing after restore'; END IF;
END $$;
SQL
docker compose exec -T control-db psql -v ON_ERROR_STOP=1 -U "$CONTROL_OWNER" -d "$CDB" <<'SQL' >/dev/null
DO $$
DECLARE migrations integer;
BEGIN
  SELECT count(*) INTO migrations FROM public.schema_migrations;
  IF migrations <= 0 THEN RAISE EXCEPTION 'control schema_migrations empty after restore'; END IF;
  IF to_regclass('billing.invoice') IS NULL THEN RAISE EXCEPTION 'billing.invoice missing after restore'; END IF;
  IF to_regclass('ops.backup_run') IS NULL THEN RAISE EXCEPTION 'ops.backup_run missing after restore'; END IF;
  IF to_regclass('ops.dr_drill') IS NULL THEN RAISE EXCEPTION 'ops.dr_drill missing after restore'; END IF;
END $$;
SQL

# Prove object storage is restorable, not merely present in the backup directory.
mkdir -p "$TMP_OBJECT_DIR/restored"
docker compose run --rm --no-deps \
  -v "$(cd "$SRC" && pwd):/backup:ro" \
  -v "$TMP_OBJECT_DIR/restored:/restore" \
  --entrypoint /bin/sh minio-init -c \
  "set -eu; mc alias set local http://minio:9000 '${S3_ACCESS_KEY:-lotediretor}' '${S3_SECRET_KEY:-lotediretor-local-secret}' >/dev/null; mc mb --ignore-existing local/'$DRILL_BUCKET' >/dev/null; mc mirror --overwrite /backup/object-storage local/'$DRILL_BUCKET'; mc mirror --overwrite local/'$DRILL_BUCKET' /restore"

( cd "$SRC/object-storage" && find . -type f -print0 | sort -z | xargs -0 -r sha256sum ) > "$TMP_OBJECT_DIR/source.sha256"
( cd "$TMP_OBJECT_DIR/restored" && find . -type f -print0 | sort -z | xargs -0 -r sha256sum ) > "$TMP_OBJECT_DIR/restored.sha256"
diff -u "$TMP_OBJECT_DIR/source.sha256" "$TMP_OBJECT_DIR/restored.sha256"
OBJECT_COUNT=$(find "$SRC/object-storage" -type f | wc -l | tr -d ' ')

RTO_SECONDS=$(( $(date +%s) - START_EPOCH ))
EVIDENCE_FILE="$DR_ARTIFACT_DIR/dr-${STAMP}.json"
cat > "$EVIDENCE_FILE" <<JSON
{
  "status":"PASS",
  "environment":"$ENVIRONMENT",
  "backupStamp":"$STAMP",
  "backupStartedEpoch":$BACKUP_START_EPOCH,
  "backupCompletedEpoch":$BACKUP_COMPLETED_EPOCH,
  "simulatedFailureEpoch":$SIMULATED_FAILURE_EPOCH,
  "rpoSeconds":$RPO_SECONDS,
  "rtoSeconds":$RTO_SECONDS,
  "databaseRestore":{"platform":"PASS","control":"PASS","criticalSchemaContracts":"PASS"},
  "objectStorageRestore":{"status":"PASS","objects":$OBJECT_COUNT,"checksumComparison":"PASS"},
  "backupChecksumManifest":"PASS",
  "classification":"LOCAL_SYNTHETIC_DR_EVIDENCE_NOT_PRODUCTION_HOMOLOGATION"
}
JSON

docker compose exec -T control-db psql -U "$CONTROL_OWNER" -d "${CONTROL_DB_NAME:-lotediretor_control}" -v ON_ERROR_STOP=1 \
  -v stamp="$STAMP" -v env_name="$ENVIRONMENT" -v src="$SRC" -v rto="$RTO_SECONDS" -v rpo="$RPO_SECONDS" -v objects="$OBJECT_COUNT" <<'SQL'
INSERT INTO ops.restore_run(backup_run_id,scope,environment,status,target_ref,evidence,completed_at,idempotency_key)
VALUES(
  (SELECT id FROM ops.backup_run WHERE idempotency_key='backup:'||:'stamp'),
  'FULL',:'env_name','SUCCEEDED',:'src',
  jsonb_build_object(
    'platform_restore','PASS','control_restore','PASS','critical_schema_contracts','PASS',
    'object_storage_restore','PASS','object_count',:'objects'::integer,'checksum_manifest_verified',true
  ),now(),'restore:'||:'stamp'
)
ON CONFLICT(idempotency_key) DO UPDATE SET status='SUCCEEDED',target_ref=excluded.target_ref,evidence=excluded.evidence,completed_at=now(),error=null;

INSERT INTO ops.dr_drill(environment,status,scenario,rpo_seconds,rto_seconds,evidence,started_at,completed_at,idempotency_key)
VALUES(
  :'env_name','PASSED','full_database_and_object_storage_restore',:'rpo'::integer,:'rto'::integer,
  jsonb_build_object(
    'backup_stamp',:'stamp','platform_restore','PASS','control_restore','PASS',
    'object_storage_restore','PASS','object_count',:'objects'::integer,'checksum_manifest_verified',true,
    'classification','LOCAL_SYNTHETIC_DR_EVIDENCE_NOT_PRODUCTION_HOMOLOGATION'
  ),now()-( :'rto'::integer * interval '1 second'),now(),'dr:'||:'stamp'
)
ON CONFLICT(idempotency_key) DO UPDATE SET
  status='PASSED',rpo_seconds=excluded.rpo_seconds,rto_seconds=excluded.rto_seconds,
  evidence=excluded.evidence,completed_at=now();
SQL

echo "Restore drill PASS: DB + object storage restored (synthetic RPO ${RPO_SECONDS}s, RTO ${RTO_SECONDS}s)."
echo "Evidence: $EVIDENCE_FILE"
