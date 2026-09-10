-- v20 production hardening: make event.outbox crash-recoverable.
-- A dispatcher claim is a lease, not a terminal state. Stale PUBLISHING rows can be
-- reclaimed after lease expiry and republished with the same event id / JetStream msgID.

ALTER TABLE event.outbox ADD COLUMN IF NOT EXISTS claimed_at timestamptz;
ALTER TABLE event.outbox ADD COLUMN IF NOT EXISTS lease_until timestamptz;
ALTER TABLE event.outbox ADD COLUMN IF NOT EXISTS claimed_by text;

-- Rescue rows that may have been stranded by the previous claim-then-publish design.
UPDATE event.outbox
SET status='FAILED',
    next_attempt_at=now(),
    claimed_at=NULL,
    lease_until=NULL,
    claimed_by=NULL,
    last_error=COALESCE(last_error,'reclaimed during outbox lease migration')
WHERE status='PUBLISHING' AND published_at IS NULL;

CREATE INDEX IF NOT EXISTS event_outbox_dispatch_idx
  ON event.outbox(status,next_attempt_at,lease_until,created_at)
  WHERE status IN ('PENDING','FAILED','PUBLISHING');
