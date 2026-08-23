# Fluxo de desenvolvimento — LoteDiretor Brasil

## Branches

- `main`: baseline estável/aprovado.
- `develop`: integração das próximas entregas.
- `feature/*`: funcionalidades.
- `fix/*`: correções.
- `chore/*`: infraestrutura, documentação e manutenção.

Novas funcionalidades não devem ser implementadas diretamente em `main`.

## Sequência padrão

1. escolher uma issue do roadmap;
2. criar branch a partir de `develop`;
3. implementar somente o escopo daquela entrega;
4. executar o validador corrente e testes específicos;
5. abrir PR para `develop`;
6. registrar no PR o que está IMPLEMENTADO, TESTADO, INTEGRADO e HOMOLOGADO;
7. corrigir CI/revisão antes do merge;
8. exigir CI verde antes do merge;
9. promover de `develop` para `main` somente em checkpoints de release.

## Regras para Codex e outros agentes

O arquivo `AGENTS.md` é obrigatório e prevalece para regras de engenharia do repositório. O Blueprint Final v2.0 continua sendo a especificação mestre do produto.

Agentes devem preservar multi-tenancy/RLS, provenance, evidência, temporalidade, rastreabilidade e limites de uso das IAs. A.I TEC não pode substituir cálculo geométrico por LLM; Solar não pode inventar dados técnicos ou comerciais; regras jurídicas não confirmadas não podem gerar conclusões decisivas.

## Prioridade de execução

A ordem atual está registrada nas issues do GitHub. O primeiro bloco é runtime reproduzível e homologação de São Paulo. Depois seguem Core/Legal, AI Core e os demais módulos do Blueprint.

## Release

Uma release só pode ser promovida como homologada quando os gates externos relevantes tiverem evidência real. Código existente, mocks ou testes estáticos não equivalem a homologação operacional.
