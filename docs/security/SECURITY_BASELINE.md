# Security baseline

- OIDC/PKCE e sessão HttpOnly.
- MFA obrigatório no Admin em produção.
- RLS em tabelas privadas.
- Segredos fora do frontend.
- Uploads futuros entram em quarentena.
- Ações irreversíveis não são executadas autonomamente por LLM.
- Support impersonation deve ser temporário/auditado e read-only por padrão.
