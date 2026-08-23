# Runtime acceptance — v10

Production/staging candidate acceptance is all-or-nothing:

1. `docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build`
2. all long-running services healthy;
3. gateway and Platform API smoke pass;
4. actual non-owner runtime RLS isolation pass;
5. database/object backup created with SHA-256;
6. restore drill passes in temporary databases.

Use `ops/runtime/acceptance.sh`. A static PASS is not a runtime PASS.
