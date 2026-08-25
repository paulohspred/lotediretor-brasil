-- v20 Admin SaaS: append-only tables may accept an identical no-op UPSERT for idempotent replay.
CREATE OR REPLACE FUNCTION admin.reject_append_only_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN RETURN NEW; END IF;
  RAISE EXCEPTION '% is append-only',TG_TABLE_SCHEMA||'.'||TG_TABLE_NAME;
END $$;
