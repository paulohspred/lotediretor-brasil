# Auditoria do marco v7 — 70% de software

A meta desta versão é funcional: nenhuma área principal recebe nota >=70 apenas por existir uma pasta ou contrato. O marco exige rotas, persistência, UI ou worker funcional correspondente.

## Gates adicionados

- **Dados:** snapshot real + SHA-256 + quality PASS + publicação ativa; configuração de fonte sozinha não é cobertura.
- **IA:** contexto técnico é reconstruído no backend. Regras `CONFIRMED` não são aceitas do navegador como verdade.
- **A.I TEC:** cenários hard-invalid não entram no ranking; export é rotulado preliminar.
- **Solar:** geração exige yield externo; financeiro guarda premissas explícitas.
- **Condomínio/Prefeitura:** extração automática permanece `CANDIDATE` até revisão humana.
- **Admin:** maker-checker executa efeitos conhecidos (ativação de plano/aprovação de deployment) dentro de transação.
- **RLS:** policies existem, mas produção ainda requer non-owner role e teste de isolamento conforme `docs/security/PRODUCTION_DB_ROLE.md`.

## Não contado como concluído

- cobertura CAR/SIGEF/IBAMA/PRODES sem snapshot oficial;
- cobertura de zoneamento nacional sem fábrica/homologação municipal;
- AVM DEMO como dado real;
- Solar/A.I TEC preliminares como projeto executivo;
- build Docker/E2E que não foi executado neste ambiente;
- HA/DR nacional sem restore/failover testados.
