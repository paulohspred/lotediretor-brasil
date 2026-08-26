-- v20 privacy hard guards.

CREATE OR REPLACE FUNCTION privacy.guard_retention_policy() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at=now();
  IF NEW.data_category IN ('AUDIT_TRAIL','LEGAL_EVIDENCE','SOURCE_PROVENANCE') THEN
    IF NEW.protected_class IS DISTINCT FROM true OR NEW.expiry_action<>'RETAIN' OR NEW.automatic_execution THEN
      RAISE EXCEPTION 'privacy_protected_class_must_be_retain_nonautomatic';
    END IF;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS retention_policy_guard ON privacy.retention_policy;
CREATE TRIGGER retention_policy_guard BEFORE INSERT OR UPDATE ON privacy.retention_policy FOR EACH ROW EXECUTE FUNCTION privacy.guard_retention_policy();

CREATE OR REPLACE FUNCTION privacy.guard_operation_event_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'privacy_operation_event_is_append_only';
END $$;
DROP TRIGGER IF EXISTS operation_event_append_only_update ON privacy.operation_event;
CREATE TRIGGER operation_event_append_only_update BEFORE UPDATE OR DELETE ON privacy.operation_event FOR EACH ROW EXECUTE FUNCTION privacy.guard_operation_event_append_only();

CREATE OR REPLACE FUNCTION privacy.guard_erasure_execution() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status='EXECUTING' AND OLD.status IS DISTINCT FROM 'EXECUTING' AND NEW.request_type='ERASURE' THEN
    IF OLD.status<>'APPROVED' THEN RAISE EXCEPTION 'privacy_erasure_requires_approved_request'; END IF;
    IF privacy.has_active_hold(NEW.tenant_id,NEW.subject_user_id,'IDENTITY') THEN RAISE EXCEPTION 'privacy_erasure_blocked_by_legal_hold'; END IF;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS subject_request_erasure_guard ON privacy.subject_request;
CREATE TRIGGER subject_request_erasure_guard BEFORE UPDATE ON privacy.subject_request FOR EACH ROW EXECUTE FUNCTION privacy.guard_erasure_execution();

COMMENT ON FUNCTION privacy.guard_retention_policy() IS 'Protected audit/legal/provenance classes are always RETAIN and never automatically destructed.';
COMMENT ON FUNCTION privacy.guard_erasure_execution() IS 'Database-level fail-closed guard: ERASURE only enters EXECUTING from APPROVED and with no active identity hold.';
