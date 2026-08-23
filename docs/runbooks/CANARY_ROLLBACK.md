# Canary and rollback

Deploy immutable artifact to canary/staging, run health + RLS + data + report + billing sandbox + load gates, then promote by approved artifact digest. Roll back application artifacts independently from immutable source snapshots. Never “fix” a bad data release by mutating historical snapshot rows; move the active publication pointer to a previously validated snapshot and record the publication event.
