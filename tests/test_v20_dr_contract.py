from pathlib import Path

root = Path(__file__).resolve().parents[1]
backup = (root / 'ops/backup/backup.sh').read_text()
restore = (root / 'ops/backup/restore-drill.sh').read_text()

for needle in [
    'backup_started_epoch=',
    'backup_completed_epoch=',
    'METADATA.txt',
    'SHA256SUMS.txt',
    'capture_window_seconds',
    'object_storage_included',
]:
    assert needle in backup, f'backup contract missing: {needle}'

# Metadata must be written before the checksum manifest is generated.
assert backup.index('cat > "$OUT/METADATA.txt"') < backup.index('sha256sum > SHA256SUMS.txt')

for needle in [
    'sha256sum -c SHA256SUMS.txt',
    'DR_SIMULATED_FAILURE_EPOCH',
    'RPO_SECONDS=',
    'RTO_SECONDS=',
    "scenario,rpo_seconds,rto_seconds",
    'full_database_and_object_storage_restore',
    'mc mirror --overwrite /backup/object-storage',
    'mc mirror --overwrite local/',
    'diff -u "$TMP_OBJECT_DIR/source.sha256" "$TMP_OBJECT_DIR/restored.sha256"',
    "to_regclass('aitec.job') IS NULL",
    "to_regclass('report.report_run') IS NULL",
    "to_regclass('billing.invoice') IS NULL",
    'LOCAL_SYNTHETIC_DR_EVIDENCE_NOT_PRODUCTION_HOMOLOGATION',
]:
    assert needle in restore, f'restore/DR contract missing: {needle}'

# A boolean SELECT would not fail a restore drill. Critical relation checks must raise.
assert 'RAISE EXCEPTION' in restore
assert 'criticalSchemaContracts' in restore
assert 'objectStorageRestore' in restore

print('v20 backup/restore synthetic RPO/RTO + object-storage DR contract OK')
