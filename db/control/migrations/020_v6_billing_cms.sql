CREATE UNIQUE INDEX IF NOT EXISTS billing_ledger_reference_uq
ON billing.ledger_entry(tenant_id,kind,reference_type,reference_id)
WHERE reference_id IS NOT NULL;

ALTER TABLE billing.webhook_event ADD COLUMN IF NOT EXISTS verified boolean NOT NULL DEFAULT false;
ALTER TABLE billing.webhook_event ADD COLUMN IF NOT EXISTS request_id text;
ALTER TABLE billing.webhook_event ADD COLUMN IF NOT EXISTS resource_id text;
ALTER TABLE billing.webhook_event ADD COLUMN IF NOT EXISTS topic text;
ALTER TABLE billing.webhook_event ADD COLUMN IF NOT EXISTS processing_at timestamptz;

INSERT INTO cms.page(slug,title,status)
VALUES('home','Home','PUBLISHED')
ON CONFLICT(slug) DO UPDATE SET title=excluded.title;

INSERT INTO cms.page_version(page_id,version,blocks,seo)
SELECT p.id,1,
 '[{"type":"hero","eyebrow":"Inteligência territorial nacional","title":"Entenda o imóvel antes de decidir.","body":"Plano Diretor, cadastro, rural, mercado, condomínio, energia solar e geração arquitetônica conectados a uma única base auditável."}]'::jsonb,
 '{"title":"LoteDiretor Brasil","description":"Inteligência urbanística, territorial e imobiliária."}'::jsonb
FROM cms.page p WHERE p.slug='home'
ON CONFLICT(page_id,version) DO NOTHING;

UPDATE cms.page p SET published_version_id=v.id,status='PUBLISHED'
FROM cms.page_version v WHERE v.page_id=p.id AND p.slug='home' AND v.version=1;

INSERT INTO release.release(version,environment,status)
VALUES('6.0.0','local','ACTIVE')
ON CONFLICT(version,environment) DO UPDATE SET status='ACTIVE';
