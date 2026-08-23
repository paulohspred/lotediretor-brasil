CREATE TABLE IF NOT EXISTS ops.incident(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  severity text NOT NULL,
  service text,
  title text NOT NULL,
  status text NOT NULL DEFAULT 'OPEN',
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  opened_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

CREATE TABLE IF NOT EXISTS ops.check_run(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  check_type text NOT NULL,
  environment text NOT NULL DEFAULT 'local',
  status text NOT NULL,
  summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS release.deployment(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  release_id uuid REFERENCES release.release(id),
  environment text NOT NULL,
  status text NOT NULL DEFAULT 'BUILT',
  artifact_digest text,
  approved_by text,
  deployed_at timestamptz,
  rolled_back_at timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS product.entitlement_audit(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid REFERENCES tenant.tenant(id),
  snapshot jsonb NOT NULL,
  source text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ai_ops_trace_created_idx ON ai_ops.trace(created_at DESC);
CREATE INDEX IF NOT EXISTS support_ticket_status_idx ON support.ticket(status,priority,created_at DESC);
CREATE INDEX IF NOT EXISTS admin_approval_status_idx ON admin.approval(status,requested_at DESC);
CREATE INDEX IF NOT EXISTS ops_service_health_latest_idx ON ops.service_health(service,checked_at DESC);

INSERT INTO release.release(version,environment,status)
VALUES('7.0.0','local','ACTIVE')
ON CONFLICT(version,environment) DO UPDATE SET status='ACTIVE';
