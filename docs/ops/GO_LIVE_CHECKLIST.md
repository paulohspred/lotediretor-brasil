# Go-live checklist — v19-rc.3

A release **não é aprovada para produção** até que cada item tenha evidência anexada:

- `package-lock.json` versionado e `npm ci` PASS a partir de checkout limpo;
- `npm run typecheck` e `npm run build` PASS com dependências instaladas;
- imagens de container construídas por digest imutável e scan de vulnerabilidades revisado;
- migrations completas executadas em clone de staging, incluindo Knowledge Plane/A.I TEC/Solar RC3; forward/rollback strategy documentada;
- runtime app role NOBYPASSRLS e testes de isolamento cross-tenant PASS; workers privilegiados restritos;
- OpenSearch reconstruído do source of truth; autorização pré-retrieval e tenant/public scope testados;
- embedding/model/reranker versionados e avaliação de retrieval registrada;
- GeoSampa/São Paulo: ingestão real, QA, publicação, lote/zona canônicos e 10–20 golden lots revisados;
- relatório ponta a ponta reproduzível para os golden lots;
- A.I Cidades/Condomínio: abstenção, temporalidade, conflito, prompt injection e tenant leakage PASS;
- A.I TEC: zero falso `conforme` para hard constraints nos golden sites; seed/reprodução e geometry gates PASS;
- Solar: entradas/datasheets/tarifas/fontes versionados; outputs preliminares claramente separados de projeto executivo;
- production security gate PASS; MFA e secrets conforme política;
- runtime acceptance PASS incluindo backup e restore drill;
- fontes externas habilitadas passam network/source preflight e possuem licença/provenance documentada;
- Mercado Pago sandbox end-to-end PASS antes de credenciais live;
- Prometheus/Grafana/Loki/Tempo/Alertmanager operacionais e alertas testados;
- browser E2E e acessibilidade PASS;
- load gate atende SLO acordado;
- pentest triado; nenhum critical/high aberto sem exceção aprovada;
- LGPD retention/DSAR aprovados;
- canary PASS; artefato anterior e rollback verificados.
