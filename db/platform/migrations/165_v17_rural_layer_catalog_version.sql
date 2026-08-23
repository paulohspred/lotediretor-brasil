-- Compatibility bridge for the v17 rural catalogue seed.
-- v17 upserts the catalogue version, so the column must exist on clean installs
-- before 170_v17_rural360.sql runs.
ALTER TABLE rural.layer_catalog
  ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;
