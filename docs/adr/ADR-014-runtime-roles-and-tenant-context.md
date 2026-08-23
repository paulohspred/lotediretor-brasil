# ADR-014 — Papéis runtime e tenant context

**Status:** accepted — v14

Owners de migration nunca atendem tráfego de aplicação. Platform API usa `lotediretor_app` non-owner/NOBYPASSRLS; workers cross-tenant possuem papéis internos non-owner com privilégios mínimos; Martin é somente leitura. Toda request privada define `app.tenant_id` localmente à transação.

Migrations precedem bootstrap de passwords, eliminando dependência de papéis ainda não criados em instalação limpa.
