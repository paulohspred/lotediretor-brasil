#!/usr/bin/env bash
set -euo pipefail
./ops/runtime/wait-healthy.sh 300
./ops/runtime/smoke.sh
./ops/rls/runtime-isolation.sh
stamp=$(date -u +%Y%m%dT%H%M%SZ)
./ops/backup/backup.sh "$stamp"
./ops/backup/restore-drill.sh "${BACKUP_DIR:-./backups}/$stamp"
echo 'Runtime acceptance PASS'
