CREATE TABLE IF NOT EXISTS ai_ops.trace(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  trace_id text NOT NULL UNIQUE,
  tenant_id uuid,
  assistant text NOT NULL,
  model text,
  status text NOT NULL,
  question text,
  evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
  rules jsonb NOT NULL DEFAULT '[]'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS support.ticket(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  tenant_id uuid REFERENCES tenant.tenant(id),
  subject text NOT NULL,
  status text NOT NULL DEFAULT 'OPEN',
  priority text NOT NULL DEFAULT 'NORMAL',
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS admin.approval(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  action text NOT NULL,
  object_type text NOT NULL,
  object_id text NOT NULL,
  requested_by text NOT NULL,
  approved_by text,
  status text NOT NULL DEFAULT 'PENDING',
  reason text,
  requested_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz
);
CREATE TABLE IF NOT EXISTS ops.service_health(
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  service text NOT NULL,
  status text NOT NULL,
  checked_at timestamptz NOT NULL DEFAULT now(),
  details jsonb NOT NULL DEFAULT '{}'::jsonb
);
INSERT INTO release.release(version,environment,status)
VALUES('5.0.0','local','ACTIVE')
ON CONFLICT(version,environment) DO UPDATE SET status=excluded.status;
