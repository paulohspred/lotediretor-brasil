-- v19: publication pointers are scoped by dataset, not only by source.
-- A single official service (e.g. municipal WFS) can publish parcel, zoning and
-- other layers independently without one activation deactivating another.
ALTER TABLE source.publication ADD COLUMN IF NOT EXISTS dataset_code text;
ALTER TABLE source.publication_event ADD COLUMN IF NOT EXISTS dataset_code text;

UPDATE source.publication p
SET dataset_code = NULLIF(s.metadata->>'dataset_code','')
FROM source.snapshot s
WHERE p.snapshot_id=s.id AND p.dataset_code IS NULL AND NULLIF(s.metadata->>'dataset_code','') IS NOT NULL;

DROP INDEX IF EXISTS source.source_publication_active_uq;
CREATE UNIQUE INDEX IF NOT EXISTS source_publication_active_dataset_uq
  ON source.publication(source_id, COALESCE(municipality_ibge,''), COALESCE(dataset_code,''))
  WHERE status='ACTIVE';

CREATE INDEX IF NOT EXISTS source_publication_dataset_idx
  ON source.publication(source_id,municipality_ibge,dataset_code,status);
