# v15 — Core Territorial

A v15 implementa o fluxo central do Blueprint sem promover descoberta de fonte a dado homologado.

## Fluxo

`ResolverInput -> Parcel candidates -> municipality -> zone(s) -> source coverage -> legal rules -> spatial relations -> calculations -> AnalysisRun -> evidence/snapshots`

Entradas do Parcel Resolver:
- coordenada;
- polígono GeoJSON;
- endereço previamente indexado e versionado;
- identificador canônico (`CIB`, inscrição municipal, matrícula de referência ou outro `asset_identifier`);
- identificador oficial da parcela.

O resolver retorna candidatos, confiança, motivo do vínculo e `requiresConfirmation`. Uma análise técnica não continua quando há ambiguidade relevante.

## Spatial Engine

`geo.layer` governa o catálogo e `geo.feature` armazena feições normalizadas com snapshot. Os domínios `ENVIRONMENT`, `RISK`, `INFRA`, `MOBILITY`, `HERITAGE` e `LICENSING` são consultados por interseção/proximidade sem duplicar a geometria por módulo.

Toda relação gravada em `analysis.spatial_relation` referencia `source_snapshot_id`.

## Legal/Temporal Engine

A estrutura jurídica passou a suportar `legal.article`, `legal.annex`, `legal.relation` e `legal.conflict`. Somente `legal.rule.status='CONFIRMED'` alimenta cálculos. Ingestão automática de HTML cria no máximo versão `REVIEWED`; não confirma regra.

## Analysis Run

A análise persiste:
- parâmetros/regras usados;
- relações espaciais;
- cálculos básicos reproduzíveis (CA/TO/TP quando existirem regras confirmadas);
- snapshots de entrada;
- findings;
- limitações explícitas.

## Município laboratório

São Paulo (`3550308`) entra como **perfil de descoberta**, não como município homologado. O perfil registra:
- GeoSampa WFS oficial;
- Catálogo oficial de Legislação Municipal / PDE;
- exigência de mapear o `typeName` exato de cada layer, revisar metadados/licença, criar snapshot, passar QA e validar lotes manualmente antes de promoção.

Nenhum layer municipal é marcado como `PUBLISHED` apenas por existir uma URL.
