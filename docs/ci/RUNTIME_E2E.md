# Runtime E2E gate

This gate closes the gap between static validation and a real containerized runtime. It is evidence for the Blueprint v2.0 local/runtime Definition of Done, not a substitute for production homologation.

## What it proves

On a clean GitHub-hosted Linux runner the workflow:

1. builds the Node application Docker images from the versioned `package-lock.json` using `npm ci`;
2. starts the real Compose stack, including PostgreSQL/PostGIS, Control DB, Valkey, NATS JetStream, MinIO, Keycloak, OpenSearch, APIs, engines, workers, web apps, Martin and Caddy;
3. waits for long-running services to be healthy and requires one-shot migration/bootstrap containers to exit with code 0;
4. verifies both schema migration ledgers exist in live PostgreSQL instances;
5. calls gateway, Platform API, Control API, AI Gateway, Solar and A.I TEC health endpoints through Caddy;
6. seeds two tenants and proves a non-owner application role cannot read or write another tenant through PostgreSQL RLS;
7. uses the real document-evidence indexer and real OpenSearch cluster, then proves lexical/hybrid retrieval respects tenant, public-municipal and temporal filters;
8. keeps chat/embedding providers optional: missing external credentials are never disguised as successful provider integration;
9. creates database/object-storage backups, verifies checksums and restores both database dumps into temporary databases;
10. captures Compose status/logs and removes volumes even on failure.

## What it does not prove

A green runtime E2E run is not production homologation. It does not by itself prove:

- external AI chat/embedding provider credentials, quality or cost controls;
- live municipal/national/licensed data-source availability or legal authority;
- São Paulo or any other municipality professional/legal homologation;
- browser user journeys, mobile behavior or WCAG review;
- production TLS/DNS, secrets manager, cloud IAM or WAF/CDN configuration;
- pentest, load/soak capacity, canary deployment or HA/DR across hosts/regions;
- professional/legal/engineering review of territorial, Solar or A.I TEC outputs.

Those remain separate gates and must not be converted to `PASS` without evidence.

## Local execution

For a local development environment using the Compose defaults:

```bash
export COMPOSE_FILE=docker-compose.yml:docker-compose.ci.yml
docker compose build
docker compose up -d
./ops/runtime/wait-healthy.sh 420
./ops/runtime/smoke.sh
./ops/rls/runtime-isolation.sh
./ops/ai/runtime-integration.sh
stamp="local-$(date -u +%Y%m%dT%H%M%SZ)"
./ops/backup/backup.sh "$stamp"
./ops/backup/restore-drill.sh "${BACKUP_DIR:-./backups}/$stamp"
docker compose down -v --remove-orphans
```

The GitHub workflow uses isolated CI-only credentials and stores short-lived diagnostics as an Actions artifact. The diagnostics are evidence of the run; they are not application data backups for production use.
