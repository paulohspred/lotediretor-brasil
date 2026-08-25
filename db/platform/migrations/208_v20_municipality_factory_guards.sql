-- v20 Municipality Factory hard gates: discovery != activation != homologation.

CREATE OR REPLACE FUNCTION municipality.guard_factory_source_transition() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE latest_snapshot uuid; required_qa text[]; qa_pass integer; latest_discovery_status text; latest_golden_status text; approved_goldens integer;
BEGIN
  NEW.updated_at=now();
  IF NEW.connector_status='ACTIVE' AND OLD.connector_status IS DISTINCT FROM 'ACTIVE' THEN
    IF NEW.license_status<>'VERIFIED' THEN RAISE EXCEPTION 'factory_activation_requires_verified_license'; END IF;
    IF NEW.contract_id IS NULL THEN RAISE EXCEPTION 'factory_activation_requires_contract'; END IF;
    SELECT d.status INTO latest_discovery_status FROM municipality.factory_discovery d WHERE d.factory_source_id=NEW.id ORDER BY d.discovered_at DESC,d.id DESC LIMIT 1;
    IF latest_discovery_status IS DISTINCT FROM 'PASS' THEN RAISE EXCEPTION 'factory_activation_requires_latest_discovery_pass'; END IF;
  END IF;
  IF NEW.homologation_status='CONFIRMED' AND OLD.homologation_status IS DISTINCT FROM 'CONFIRMED' THEN
    IF NEW.connector_status<>'ACTIVE' OR NEW.license_status<>'VERIFIED' THEN RAISE EXCEPTION 'factory_homologation_requires_active_licensed_connector'; END IF;
    IF NEW.reviewed_by IS NULL OR NEW.reviewed_at IS NULL OR nullif(trim(NEW.review_reason),'') IS NULL THEN RAISE EXCEPTION 'factory_homologation_requires_human_review'; END IF;
    SELECT r.source_snapshot_id INTO latest_snapshot FROM municipality.factory_connector_run r
      WHERE r.factory_source_id=NEW.id AND r.run_kind='INGEST' AND r.status='SUCCEEDED' AND r.source_snapshot_id IS NOT NULL
      ORDER BY r.finished_at DESC NULLS LAST,r.started_at DESC,r.id DESC LIMIT 1;
    IF latest_snapshot IS NULL THEN RAISE EXCEPTION 'factory_homologation_requires_successful_ingest'; END IF;
    SELECT CASE c.media_class WHEN 'GIS' THEN ARRAY['GIS','STRUCTURE','LICENSE','TEMPORAL']::text[] WHEN 'DOCUMENT' THEN ARRAY['LEGAL','STRUCTURE','LICENSE','TEMPORAL']::text[] ELSE ARRAY['GIS','LEGAL','STRUCTURE','LICENSE','TEMPORAL']::text[] END
      INTO required_qa FROM source.connector_contract c WHERE c.id=NEW.contract_id;
    IF required_qa IS NULL THEN RAISE EXCEPTION 'factory_homologation_requires_contract'; END IF;
    SELECT count(DISTINCT q.qa_kind) INTO qa_pass FROM municipality.factory_qa_result q
      WHERE q.factory_source_id=NEW.id AND q.source_snapshot_id=latest_snapshot AND q.status='PASS' AND q.qa_kind=ANY(required_qa);
    IF qa_pass<>cardinality(required_qa) THEN RAISE EXCEPTION 'factory_homologation_requires_all_qa_pass'; END IF;
    SELECT g.status INTO latest_golden_status FROM municipality.factory_golden_run g
      WHERE g.factory_source_id=NEW.id AND g.source_snapshot_id=latest_snapshot
      ORDER BY g.run_at DESC,g.id DESC LIMIT 1;
    IF latest_golden_status IS DISTINCT FROM 'PASS' THEN RAISE EXCEPTION 'factory_homologation_requires_latest_golden_pass'; END IF;
    IF NOT EXISTS(SELECT 1 FROM municipality.factory_golden_run g WHERE g.factory_source_id=NEW.id AND g.source_snapshot_id=latest_snapshot AND g.status='PASS' AND g.total_cases>0 AND g.passed_cases=g.total_cases ORDER BY g.run_at DESC,g.id DESC LIMIT 1) THEN RAISE EXCEPTION 'factory_homologation_requires_complete_golden_pass'; END IF;
    SELECT count(*) INTO approved_goldens FROM municipality.factory_golden_case gc WHERE gc.municipality_tenant_id=NEW.municipality_tenant_id AND gc.dataset_code=NEW.dataset_code AND gc.active AND gc.professional_review_status='APPROVED';
    IF approved_goldens=0 THEN RAISE EXCEPTION 'factory_homologation_requires_professionally_reviewed_golden'; END IF;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS factory_source_transition_guard ON municipality.factory_source;
CREATE TRIGGER factory_source_transition_guard BEFORE UPDATE ON municipality.factory_source FOR EACH ROW EXECUTE FUNCTION municipality.guard_factory_source_transition();

CREATE OR REPLACE FUNCTION municipality.guard_factory_candidate_confirmation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status='CONFIRMED' AND OLD.status IS DISTINCT FROM 'CONFIRMED' THEN
    IF NEW.reviewed_by IS NULL OR NEW.reviewed_at IS NULL OR nullif(trim(NEW.review_reason),'') IS NULL THEN RAISE EXCEPTION 'candidate_confirmation_requires_human_review'; END IF;
    IF NOT EXISTS(SELECT 1 FROM municipality.factory_qa_result q WHERE q.factory_source_id=NEW.factory_source_id AND q.source_snapshot_id=NEW.source_snapshot_id AND q.status='PASS') THEN RAISE EXCEPTION 'candidate_confirmation_requires_qa_pass'; END IF;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS factory_candidate_confirmation_guard ON municipality.factory_rule_candidate;
CREATE TRIGGER factory_candidate_confirmation_guard BEFORE UPDATE ON municipality.factory_rule_candidate FOR EACH ROW EXECUTE FUNCTION municipality.guard_factory_candidate_confirmation();

CREATE OR REPLACE FUNCTION municipality.guard_factory_terminal_run() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status IN ('SUCCEEDED','FAILED','BLOCKED') AND NEW IS DISTINCT FROM OLD THEN RAISE EXCEPTION 'factory_terminal_run_is_immutable'; END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS factory_terminal_run_guard ON municipality.factory_connector_run;
CREATE TRIGGER factory_terminal_run_guard BEFORE UPDATE ON municipality.factory_connector_run FOR EACH ROW EXECUTE FUNCTION municipality.guard_factory_terminal_run();

CREATE OR REPLACE FUNCTION municipality.refresh_factory_coverage_snapshot() RETURNS uuid
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public,municipality,source,core AS $$
DECLARE out_id uuid; adapters jsonb; ufs jsonb;
BEGIN
  SELECT coalesce(jsonb_object_agg(adapter,cnt),'{}'::jsonb) INTO adapters FROM (SELECT adapter,count(*)::integer cnt FROM municipality.factory_source GROUP BY adapter ORDER BY adapter) x;
  SELECT coalesce(jsonb_object_agg(uf,cnt),'{}'::jsonb) INTO ufs FROM (
    SELECT coalesce(m.uf,'UNKNOWN') uf,count(DISTINCT fs.municipality_ibge)::integer cnt
    FROM municipality.factory_source fs LEFT JOIN core.municipality m ON m.ibge_code=fs.municipality_ibge GROUP BY coalesce(m.uf,'UNKNOWN') ORDER BY 1
  ) x;
  INSERT INTO municipality.factory_coverage_snapshot(municipality_count,source_count,active_connector_count,confirmed_source_count,unavailable_source_count,latest_qa_pass_count,latest_golden_pass_count,by_adapter,by_uf,metadata)
  SELECT count(DISTINCT municipality_ibge)::integer,count(*)::integer,count(*) FILTER(WHERE connector_status='ACTIVE')::integer,count(*) FILTER(WHERE homologation_status='CONFIRMED')::integer,count(*) FILTER(WHERE connector_status='UNAVAILABLE' OR homologation_status='UNAVAILABLE')::integer,(SELECT count(*)::integer FROM municipality.factory_qa_result q WHERE q.status='PASS'),(SELECT count(*)::integer FROM municipality.factory_golden_run g WHERE g.status='PASS'),adapters,ufs,jsonb_build_object('factory_version','municipality-factory-v20.1') FROM municipality.factory_source RETURNING id INTO out_id;
  RETURN out_id;
END $$;
GRANT EXECUTE ON FUNCTION municipality.refresh_factory_coverage_snapshot() TO lotediretor_worker;

COMMENT ON TABLE municipality.factory_rule_candidate IS 'Machine/parser output only. CANDIDATE is the default and confirmation requires human review + QA; no ingestion path may auto-homologate.';
COMMENT ON COLUMN municipality.factory_source.homologation_status IS 'CONFIRMED is guarded by successful ingest, complete QA, latest golden PASS and professional human review.';
