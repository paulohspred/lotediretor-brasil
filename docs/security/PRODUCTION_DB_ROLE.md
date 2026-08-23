# PostgreSQL, RLS e papel de aplicação — v7

A árvore v7 possui políticas RLS nos domínios privados e as novas operações transacionais definem `app.tenant_id`. Isso **não basta, isoladamente, para declarar isolamento de produção homologado**.

## Regra de produção

O usuário de runtime da Platform API deve ser um papel PostgreSQL **não proprietário das tabelas**, sem `BYPASSRLS`. O papel usado para migrations deve ser separado do papel de runtime. Para cada operação privada, a conexão/transação deve definir `app.tenant_id` antes de consultar ou gravar tabelas protegidas.

A configuração local ainda usa o proprietário do banco para manter o ambiente Foundation compatível. Portanto o RLS local é uma defesa estrutural, mas o teste de isolamento real com papel non-owner permanece critério obrigatório antes de produção.

## Critérios de homologação

1. criar `lotediretor_app` sem `SUPERUSER`, sem `BYPASSRLS` e sem ownership;
2. conceder somente `CONNECT`, `USAGE`, DML e sequência estritamente necessários;
3. usar credencial de migration separada;
4. executar testes A/B com dois tenants e comprovar que cada tenant recebe zero linhas do outro;
5. confirmar que requests sem `app.tenant_id` não enxergam tabelas privadas;
6. manter Admin Control Plane separado e sem SQL arbitrário.
