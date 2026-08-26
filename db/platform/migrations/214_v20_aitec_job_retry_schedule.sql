-- v20: durable retry scheduling for asynchronous A.I TEC jobs.
-- Retries must not hot-loop during transient engine/network outages.

ALTER TABLE aitec.job
  ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS aitec_job_ready_idx
  ON aitec.job(status,next_attempt_at,created_at,id)
  WHERE status='QUEUED';

-- Keep existing queued rows immediately eligible after upgrading.
UPDATE aitec.job
   SET next_attempt_at=coalesce(next_attempt_at,now())
 WHERE status='QUEUED';
