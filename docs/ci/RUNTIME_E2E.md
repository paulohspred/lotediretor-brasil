# Runtime E2E gate

This gate closes the gap between static validation and a real containerized runtime.

## What it proves

On a clean GitHub-hosted Linux runner the workflow:

1. builds the application Docker images from the versioned `package-lock.json` using `npm ci`;
2. starts the real Compose stack, including PostgreSQL/PostGIS, Control DB, Valkey, NATS, MinIO, Keycloak, OpenSearch, APIs, engines, workers, web apps, Martin and Caddy;
3. waits for long-running services to be healthy and requires one-shot migration/bootstrap containers to exit with code 0;
4. verifies both schema migration ledgers exist in live PostgreSQL instances;
5. calls gateway, Platform API, Control API, AI Gateway, Solar and A.I TEC health endpoints through Caddy;
6. seeds two tenants and proves a non-owner application role cannot read or write another tenant through RLS;
7. creates database/object-storage backups, verifies checksums and restores database dumps into temporary databases;
8. captures Compose status/logs and removes volumes even on failure.

## What it does not prove

A green runtime E2E run is not production homologation. It does not by itself prove:

- external AI chat/embedding provider credentials or quality;
- live municipal/national data-source availability;
- browser user journeys and accessibility;
- production TLS/DNS, secrets manager or cloud IAM;
- pentest, load/soak capacity, canary or HA/DR across hosts/regions;
- professional/legal/engineering review of domain outputs.

Those remain separate gates and must not be converted to `PASS` without evidence.

## Local execution

For a local development environment using the Compose defaults:

```bash
docker compose build
docker compose up -d
./ops/runtime/acceptance.sh
docker compose down -v --remove-orphans
```

The GitHub workflow uses isolated CI-only credentials and stores short-lived diagnostics as an Actions artifact.
