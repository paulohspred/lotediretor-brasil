# RE Rural 360 — arquitetura funcional v17

## Regra central

O `rural.asset` é apenas a âncora física interna. Ele **não substitui** CAR, SNCR/CCIR, SIGEF, CIB/CAFIR, matrícula, embargo IBAMA, PRODES ou SICOR. Cada registro permanece separado, com `source_snapshot_id`, vigência, geometria e identificadores próprios.

## Grafo de identidade

- `rural.registry_record`: registro normalizado por fonte.
- `rural.registry_identifier`: CAR/SNCR/CCIR/SIGEF/CIB etc. sem usar CPF/CNPJ bruto.
- `rural.geometry_version`: geometria versionada e hash.
- `rural.identity_link`: convergência entre registros; automação cria apenas `CANDIDATE`.
- `rural.party_entity` / `party_link`: suporte a entidade sensível tokenizada por conectores autorizados.

A geração automática usa coincidência de identificador normalizado e sobreposição geométrica apenas como **evidência de convergência**. A confirmação exige revisão administrativa. Nenhum desses links prova domínio.

## Busca

`GET /api/v1/rural/search` pesquisa registros e feições oficiais publicadas, com data-base e filtro espacial. A resposta padrão remove atributos com chaves sensíveis. Snapshots históricos não ativos não entram no conjunto de feições correntes.

## Sobreposição

`POST /api/v1/rural/assets/{id}/overlaps/recalculate` calcula contra:

1. geometrias dos registros ligados ao asset;
2. feições de `rural.layer_feature` pertencentes ao snapshot atualmente publicado.

O resultado preserva `source_snapshot_id` e o tipo da origem.

## Monitoramento

`rural-monitor-worker` executa monitores ativos periodicamente. O estado canônico inclui registros normalizados e feições das publicações ativas. Mudança de hash gera:

- `rural.monitor_checkpoint`;
- `rural.monitor_event`;
- notificação do tenant;
- `rural.monitor.changed` no outbox.

PRODES é monitoramento territorial, não classificação automática de infração.

## Exportações

`rural-export-worker` produz KML/KMZ. O asset interno e cada geometria cadastral aparecem como objetos separados. O arquivo recebe SHA-256 e vai para object storage.

## Dossiê Rural 360

`POST /api/v1/rural/assets/{id}/report` cria um `report.report_run` com template `RURAL360_360`. O report worker congela registros, links, overlaps, monitoramento, snapshots e evidências em PDF + manifesto JSON.

## Fonte e disponibilidade

Código de integração não equivale a cobertura. CAR/SIGEF/SNCR/CIB/IBAMA/PRODES/SICOR só podem aparecer como confirmados quando existir snapshot real, provenance/licença e quality gate compatível.
