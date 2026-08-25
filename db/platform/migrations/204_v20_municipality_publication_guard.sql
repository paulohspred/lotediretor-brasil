-- v20: defense-in-depth for auditable municipal publication transitions.
-- A rollback may only point to a snapshot that was published in an earlier transaction.

CREATE OR REPLACE FUNCTION municipality.validate_publication_event_v20()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target municipality.dataset_snapshot%ROWTYPE;
DECLARE previous municipality.dataset_snapshot%ROWTYPE;
BEGIN
  IF NEW.new_dataset_snapshot_id IS NOT NULL THEN
    SELECT * INTO target FROM municipality.dataset_snapshot WHERE id=NEW.new_dataset_snapshot_id;
    IF target.id IS NULL OR target.dataset_id<>NEW.dataset_id OR target.municipality_tenant_id<>NEW.municipality_tenant_id THEN
      RAISE EXCEPTION 'publication_event_target_snapshot_mismatch';
    END IF;
  END IF;
  IF NEW.previous_dataset_snapshot_id IS NOT NULL THEN
    SELECT * INTO previous FROM municipality.dataset_snapshot WHERE id=NEW.previous_dataset_snapshot_id;
    IF previous.id IS NULL OR previous.dataset_id<>NEW.dataset_id OR previous.municipality_tenant_id<>NEW.municipality_tenant_id THEN
      RAISE EXCEPTION 'publication_event_previous_snapshot_mismatch';
    END IF;
  END IF;
  IF NEW.action='ROLLBACK' THEN
    IF target.id IS NULL OR target.published_at IS NULL OR target.published_at>=transaction_timestamp() THEN
      RAISE EXCEPTION 'rollback_requires_previously_published_snapshot';
    END IF;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS municipality_publication_event_guard ON municipality.publication_event_v20;
CREATE TRIGGER municipality_publication_event_guard BEFORE INSERT OR UPDATE OF action,previous_dataset_snapshot_id,new_dataset_snapshot_id
ON municipality.publication_event_v20 FOR EACH ROW EXECUTE FUNCTION municipality.validate_publication_event_v20();
