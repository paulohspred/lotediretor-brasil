-- v19-rc.1: AI knowledge plane metadata, public/private retrieval safety and reindex invalidation.
-- The relational source of truth remains authoritative. OpenSearch is a derived index.

ALTER TABLE ingest.document_text ALTER COLUMN tenant_id DROP NOT NULL;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS document_title text;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS source_locator text;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS page_number integer;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS section_id text;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS scope_id text;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS municipality_ibge text;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS visibility text NOT NULL DEFAULT 'PRIVATE';
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS knowledge_status text NOT NULL DEFAULT 'DRAFT';
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS retrieval_allowed boolean NOT NULL DEFAULT false;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS valid_from timestamptz;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS valid_to timestamptz;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS recorded_at timestamptz;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS superseded_at timestamptz;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS document_version_id uuid REFERENCES legal.document_version(id) ON DELETE CASCADE;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS source_snapshot_id uuid REFERENCES source.snapshot(id) ON DELETE SET NULL;
ALTER TABLE ingest.document_text ADD COLUMN IF NOT EXISTS acl jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS ingest_document_text_public_scope_idx
  ON ingest.document_text(domain,municipality_ibge,knowledge_status,created_at DESC)
  WHERE visibility='PUBLIC' AND retrieval_allowed;
CREATE INDEX IF NOT EXISTS ingest_document_text_private_scope_idx
  ON ingest.document_text(tenant_id,domain,scope_id,knowledge_status,created_at DESC)
  WHERE tenant_id IS NOT NULL AND retrieval_allowed;
CREATE INDEX IF NOT EXISTS ingest_document_text_legal_version_idx ON ingest.document_text(document_version_id);
CREATE INDEX IF NOT EXISTS ingest_document_text_validity_idx ON ingest.document_text(valid_from,valid_to);

-- Existing private condominium text becomes searchable only after successful processing.
UPDATE ingest.document_text t
SET document_title=d.title,
    scope_id=d.condominium_id::text,
    visibility='PRIVATE',
    knowledge_status=d.processing_status,
    retrieval_allowed=(d.processing_status='PROCESSED'),
    source_locator=coalesce(t.source_locator, t.metadata->>'locator', format('document:%s#chunk-%s',t.document_id,t.chunk_index)),
    page_number=coalesce(t.page_number, nullif(t.metadata->>'page_number','')::integer)
FROM condo.document d
WHERE t.domain='condo' AND t.document_id=d.id;

-- Existing municipal uploads inherit canonical legal-version state. EXTRACTED/DRAFT content is not released to AI retrieval.
UPDATE ingest.document_text t
SET document_title=d.title,
    scope_id=d.municipality_tenant_id::text,
    municipality_ibge=mt.municipality_ibge,
    visibility=coalesce(ld.visibility,'INSTITUTIONAL'),
    knowledge_status=coalesce(dv.status,d.processing_status,'DRAFT'),
    retrieval_allowed=(coalesce(dv.status,'') IN ('REVIEWED','PUBLISHED','ACTIVE','CONFIRMED')),
    valid_from=dv.valid_from,
    valid_to=dv.valid_to,
    recorded_at=dv.recorded_at,
    superseded_at=dv.superseded_at,
    document_version_id=dv.id,
    source_snapshot_id=dv.source_snapshot_id,
    source_locator=coalesce(t.source_locator, t.metadata->>'locator', format('document:%s#chunk-%s',t.document_id,t.chunk_index)),
    page_number=coalesce(t.page_number, nullif(t.metadata->>'page_number','')::integer)
FROM municipality.document d
JOIN municipality.tenant mt ON mt.id=d.municipality_tenant_id
LEFT JOIN legal.document ld ON ld.id=d.legal_document_id
LEFT JOIN legal.document_version dv ON dv.id=d.legal_document_version_id
WHERE t.domain='municipality' AND t.document_id=d.id;

CREATE OR REPLACE FUNCTION ingest.invalidate_legal_version_index() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  UPDATE ingest.document_text
  SET indexed_at=NULL,index_error=NULL,
      knowledge_status=NEW.status,
      retrieval_allowed=(NEW.status IN ('REVIEWED','PUBLISHED','ACTIVE','CONFIRMED')),
      valid_from=NEW.valid_from,valid_to=NEW.valid_to,recorded_at=NEW.recorded_at,superseded_at=NEW.superseded_at,
      source_snapshot_id=NEW.source_snapshot_id
  WHERE document_version_id=NEW.id;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_ai_reindex_legal_version ON legal.document_version;
CREATE TRIGGER trg_ai_reindex_legal_version
AFTER UPDATE OF status,valid_from,valid_to,source_snapshot_id,superseded_at ON legal.document_version
FOR EACH ROW EXECUTE FUNCTION ingest.invalidate_legal_version_index();

CREATE OR REPLACE FUNCTION ingest.invalidate_condo_document_index() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  UPDATE ingest.document_text
  SET indexed_at=NULL,index_error=NULL,
      knowledge_status=NEW.processing_status,
      retrieval_allowed=(NEW.processing_status='PROCESSED')
  WHERE domain='condo' AND document_id=NEW.id;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_ai_reindex_condo_document ON condo.document;
CREATE TRIGGER trg_ai_reindex_condo_document
AFTER UPDATE OF processing_status ON condo.document
FOR EACH ROW EXECUTE FUNCTION ingest.invalidate_condo_document_index();

-- Private/public rows use different RLS semantics. Public rows are readable to authenticated tenant sessions,
-- while writes remain restricted to service/owner roles because tenant users have no direct DML path.
DROP POLICY IF EXISTS tenant_isolation ON ingest.document_text;
CREATE POLICY tenant_isolation ON ingest.document_text
USING (
  visibility='PUBLIC'
  OR tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid
)
WITH CHECK (
  tenant_id = nullif(current_setting('app.tenant_id',true),'')::uuid
);
ALTER TABLE ingest.document_text ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingest.document_text FORCE ROW LEVEL SECURITY;
