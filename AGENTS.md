# LoteDiretor Brasil — instruções para agentes de código

## Autoridade de produto

1. O **Blueprint Final v2.0** é a especificação mestre do produto.
2. A Seção 32 do Blueprint consolida a arquitetura definitiva e prevalece sobre alternativas técnicas históricas.
3. Não declarar funcionalidade como concluída apenas porque existem arquivos, endpoints, tabelas ou mocks.
4. Diferenciar sempre: `IMPLEMENTADO`, `TESTADO`, `INTEGRADO` e `HOMOLOGADO`.
5. `productionHomologated` permanece `false` até existirem evidências dos gates operacionais reais.

## Regras de engenharia

- Não trabalhar diretamente em `main` para novas funcionalidades. Use `develop` e branches `feature/*`, `fix/*` ou `chore/*`.
- Preserve multi-tenancy, RLS, provenance, evidence, temporalidade e auditabilidade.
- Dados privados nunca podem atravessar tenants.
- IA jurídica ou regulatória não pode inventar regra, fonte, vigência ou número; deve abster-se quando a evidência for insuficiente.
- A.I TEC deve usar motores geométricos/determinísticos para regras duras; LLM não substitui solver.
- Solar não deve inventar irradiância, tarifa, datasheet, capacidade estrutural ou capacidade de conexão.
- Não marcar outputs preliminares como projeto executivo/aprovado.
- Integrações externas só podem ser consideradas homologadas após teste real e evidência reproduzível.

## Gates mínimos por alteração

Antes de abrir PR:

1. executar o validador da versão corrente (`./validate-v19-rc3.sh` enquanto RC3 for o baseline);
2. rodar testes específicos do módulo alterado;
3. preservar regressões anteriores;
4. atualizar migrations/contratos/documentação quando necessário;
5. documentar limitações e gates externos não executados;
6. não mascarar falhas de infraestrutura como PASS.

## Prioridade atual

1. runtime reproduzível: lockfile, `npm ci`, typecheck/build;
2. PostgreSQL/PostGIS real + migrations + RLS cross-tenant;
3. Docker E2E;
4. São Paulo ponta a ponta com GeoSampa e golden lots humanos;
5. OpenSearch/embeddings/reranker/providers reais + evals;
6. depois aprofundar Rule/Legal Engine, A.I TEC, Solar, Imóvel 360, RE Rural, Condomínio, Prefeitura, Admin e Factory Brasil.

## Forma de entrega

Cada PR deve explicar:

- problema resolvido;
- arquivos e migrations alterados;
- testes executados;
- evidência de regressão;
- riscos conhecidos;
- itens ainda não homologados;
- impacto sobre o Blueprint/Definition of Done.
