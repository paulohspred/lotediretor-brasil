# RC3 — GitHub CI hardening

O primeiro CI completo em runner limpo revelou dois contratos que não apareciam no gate local sem dependências/runtime completos:

1. os tipos atuais de `pg` tratam `QueryResult.rowCount` como `number | null` e exigem `QueryResultRow` para o generic de consulta;
2. o `ai-gateway` participa do compose padrão e depende de OpenSearch, portanto OpenSearch também precisa fazer parte do grafo padrão do compose; manter apenas a dependência dentro de um profile tornava `docker compose config` inválido.

A correção desta branch mantém o comportamento funcional existente e torna esses contratos explícitos. O CI deve provar, em ordem: instalação limpa, validador RC3, typecheck, build e validação dos arquivos Compose.

Esta evidência não equivale a homologação de runtime Docker ou produção; subir os serviços, aplicar migrations, testar RLS e executar E2E continuam sendo gates separados.
