-- Runtime repair for fresh installs before v17 seeds rural.layer_catalog.
-- v17 upserts refer to EXCLUDED.version, so the catalog must expose a stable
-- schema-level version column before 170_v17_rural360.sql is applied.
ALTER TABLE rural.layer_catalog
  ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;
