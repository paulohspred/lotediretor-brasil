-- v7 search/index operationalization. PostgreSQL FTS is the always-available baseline;
-- OpenSearch indexing is optional and only marks rows indexed after a successful write.
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS indexed_at timestamptz;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS index_error text;
CREATE INDEX IF NOT EXISTS ingest_document_text_pending_index_idx ON ingest.document_text(created_at) WHERE indexed_at IS NULL;
CREATE INDEX IF NOT EXISTS ingest_document_text_tenant_domain_idx ON ingest.document_text(tenant_id,domain,created_at DESC);
