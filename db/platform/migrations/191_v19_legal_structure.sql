-- v19: stable linkage between municipal uploads and the canonical legal corpus.
ALTER TABLE municipality.document ADD COLUMN IF NOT EXISTS legal_document_id uuid REFERENCES legal.document(id);
ALTER TABLE municipality.document ADD COLUMN IF NOT EXISTS legal_document_version_id uuid REFERENCES legal.document_version(id);
CREATE INDEX IF NOT EXISTS municipality_document_legal_doc_idx ON municipality.document(legal_document_id);
CREATE INDEX IF NOT EXISTS municipality_document_legal_version_idx ON municipality.document(legal_document_version_id);
