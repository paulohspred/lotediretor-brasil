-- v20: provenance parity for legacy municipal tax records.
ALTER TABLE municipality.iptu_record ADD COLUMN IF NOT EXISTS source_snapshot_id uuid REFERENCES source.snapshot(id);
ALTER TABLE municipality.iptu_record ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS municipality_iptu_source_snapshot_idx ON municipality.iptu_record(municipality_tenant_id,source_snapshot_id,reference_year);
