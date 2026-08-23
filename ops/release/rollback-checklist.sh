#!/usr/bin/env bash
set -euo pipefail
cat <<'EOF'
Rollback is approved only when:
1. previous immutable artifact digest is known;
2. DB migrations are backward-compatible or an approved down/restore plan exists;
3. source publication pointers are not silently rewritten;
4. backup integrity is verified before destructive restore;
5. incident/audit record captures approver, reason and timestamps.
EOF
