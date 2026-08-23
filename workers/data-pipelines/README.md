# Data Pipelines — v14

Worker operacional de ingestão versionada. O IBGE Localidades possui conector ativo. CAR, SIGEF, IBAMA Embargos e PRODES podem ser ativados por URL oficial configurada em ambiente e passam pelo mesmo fluxo: raw imutável no object storage → SHA-256 → snapshot → quality checks → carga PostGIS → publicação atômica. Sem URL oficial configurada, permanecem `CONFIGURED_NOT_INGESTED`.

O adaptador federal v14 aceita endpoint que devolva `GeoJSON FeatureCollection` em EPSG:4326. WFS/arquivos compactados ou APIs autenticadas com formatos distintos exigem adaptador específico antes de serem declarados ativos.

## v15 — município laboratório

`municipality_lab.py` adiciona onboarding controlado para fontes WFS municipais. Um `typeName` deve ser explicitamente mapeado e uma URL de termos/licença deve ser fornecida antes da carga. `legal_ingest.py` preserva HTML/texto/hash e estrutura artigos, mas nunca cria regra `CONFIRMED` automaticamente.
