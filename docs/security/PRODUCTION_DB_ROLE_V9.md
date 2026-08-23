# v9 — PostgreSQL runtime isolation

Production uses distinct credentials:

- `PLATFORM_DB_MIGRATION_USER`: owner/DDL only during migrations.
- `PLATFORM_DB_APP_USER=lotediretor_app`: non-owner, `NOBYPASSRLS`, API DML only.
- `PLATFORM_DB_TILES_USER=lotediretor_tiles`: read-only `tiles` schema only.

Private-domain tables use `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`. Every private API transaction must call `set_config('app.tenant_id', tenantId, true)` before DML. `ops/rls/runtime-isolation.sh` connects as the actual runtime login role and must pass before release.
