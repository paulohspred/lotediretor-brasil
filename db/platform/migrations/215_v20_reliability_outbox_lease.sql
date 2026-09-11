-- v20 production hardening: recover crash-stuck outbox publications with a claim lease.
-- Additive migration only; historical migration 140 remains immutable.

ALTER TABLE event.outbox ADD COLUMN IF NOT EXISTS claimed_by text;
ALTER TABLE event.outbox ADD COLUMN IF NOT EXISTS claimed_at timestamptz;
ALTER TABLE event.outbox ADD COLUMN IF NOT EXISTS lease_until timestamptz;

-- Rows left in PUBLISHING by a dispatcher crash before this migration have no lease.
-- Make them immediately reclaimable after the upgraded dispatcher starts.
UPDATE event.outbox
SET lease_until=now()-interval '1 second'
WHERE status='PUBLISHING' AND lease_until IS NULL;

CREATE INDEX IF NOT EXISTS event_outbox_publish_lease_idx
ON event.outbox(lease_until,created_at)
WHERE status='PUBLISHING';

COMMENT ON COLUMN event.outbox.claimed_by IS 'Dispatcher instance currently owning the publication claim; advisory and lease-bound.';
COMMENT ON COLUMN event.outbox.claimed_at IS 'Timestamp when the current dispatcher claim was acquired.';
COMMENT ON COLUMN event.outbox.lease_until IS 'Claim expiry. Expired PUBLISHING rows are eligible for at-least-once recovery.';
