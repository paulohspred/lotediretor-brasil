# LoteDiretor Brasil — v20 pre-homologação

Implementação cumulativa do **LoteDiretor Brasil** contra o Blueprint Final v2.0. O branch v20 atual consolida Core Territorial/Legal, Imóvel 360/Rural, Condomínio, Energia Solar, A.I TEC, Prefeitura, Admin SaaS, Municipality Factory, AI Knowledge Plane e os gates operacionais necessários antes da homologação final.

`productionHomologated=false` permanece obrigatório. Fixtures locais, dados sintéticos, testes Docker e contratos de staging/release não são evidência de fonte oficial, pentest independente, revisão profissional ou infraestrutura de produção.

## Desenvolvimento local

O caminho mais simples usa Docker Compose. `docker-compose.override.yml` é carregado automaticamente no desenvolvimento e inclui o `aitec-worker`, portanto jobs A.I TEC persistidos não ficam sem consumidor.

```bash
docker compose up -d --build
docker compose ps
```

Para desmontar incluindo volumes locais:

```bash
docker compose down -v --remove-orphans
```

Credenciais/defaults desse modo são **fixtures de desenvolvimento** e não devem ser reutilizados em staging ou produção.

## Validação estática

```bash
./validate-v19-rc3.sh
python tests/validate_v20_core_legal.py
python tests/validate_v20_aitec_advanced.py
python tests/validate_v20_solar.py
python tests/validate_v20_property_rural.py
python tests/validate_v20_condo.py
python tests/validate_v20_municipality.py
python tests/validate_v20_admin_saas.py
python tests/validate_v20_municipality_factory.py
python tests/validate_v20_privacy.py
python tests/test_v20_dr_contract.py
python tests/test_v20_cortex_qualification.py
python tests/test_v20_supply_chain.py
```

O workflow `.github/workflows/ci.yml` executa também lockfile/npm, typecheck/build, contratos AI, Compose, Prometheus, production parity, staging parity estrutural, SBOM/supply-chain, release imutável e rollback self-test.

## Qualificação local final para Cortex

A qualificação principal é executada inteiramente com Docker:

```bash
bash ops/cortex/qualify-local.sh ci
```

Perfis prolongados:

```bash
bash ops/cortex/qualify-local.sh soak
bash ops/cortex/qualify-local.sh capacity
```

O harness executa, registra duração/status e preserva evidências para:

- production/staging structural parity, promoção imutável e rollback contract;
- build/health/smoke;
- A.I TEC runtime + fila persistida;
- RLS cross-tenant;
- LGPD/retenção/legal hold;
- Municipality Factory;
- OpenSearch/AI tenant-public-temporal isolation;
- OIDC real via Keycloak;
- browser desktop/mobile e axe WCAG A/AA;
- jornadas `análise → relatório`, `billing → entitlement`, `condo upload → chat` e `A.I TEC job`;
- security baseline;
- supply-chain inventory + CycloneDX SBOM;
- k6 `ci/soak/capacity`;
- fault injection e recuperação;
- métricas/traces/logs/alertas;
- backup/restore de PostgreSQL e object storage, com RPO/RTO sintéticos locais.

Artefatos ficam em `runtime-artifacts/cortex/<timestamp>/`, incluindo `gate-status.tsv`, `qualification-report.json`, `qualification-report.md` e `evidence-manifest.json`.

Consulte `docs/CORTEX_LOCAL_QUALIFICATION.md` para o procedimento detalhado.

## Release e produção

O modelo de promoção usa `docker-compose.production.yml` + `docker-compose.release.yml`. Os serviços próprios são promovidos por referências imutáveis `image@sha256`; `platform-migrate` e `control-migrate` reutilizam exatamente os mesmos artefatos das APIs correspondentes. O ambiente de aplicação não recebe DSNs de migration-owner.

O repositório contém contratos executáveis para:

- production parity;
- staging parity estrutural;
- SBOM/supply-chain;
- canary com health + AI eval + carga;
- rollback candidato → digest anterior;
- SLOs/alertas/runbooks;
- backup/restore e DR sintético local.

Essas capacidades não equivalem a execução real no ambiente final.

## Gates que continuam externos

Mesmo com a qualificação local integralmente verde, **não** marcar produção como homologada sem evidência real para:

- pentest independente e fechamento de todos os achados Critical/High;
- staging/cloud equivalente à produção e escolha formal do provedor/IaC;
- TLS/IAM/secrets/DNS/registry reais;
- canary e rollback executados no ambiente final;
- PITR/failover/HA/DR reais com RPO/RTO medidos;
- fontes oficiais, licenças e providers reais;
- golden lots e revisão jurídica/arquitetônica/engenharia/fiscal/institucional;
- proteção administrativa da branch `main`.

Consulte `STATUS.md`, `PROGRESS.json`, `VALIDATION.md`, `docs/V20_ACCEPTANCE_MATRIX.md`, `docs/architecture/BLUEPRINT_V20_GAP_MATRIX.md` e o issue #13 para o estado de homologação.
