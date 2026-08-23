# Status de integração de fontes — v17

`CONFIGURED` ou presença de código de conector **não significa dado ingerido**. Uma fonte só entra em conclusão técnica quando existe `source.snapshot` real, provenance/licença compatível, quality checks aprovados e `source.publication` ativa.

| Fonte | Estado de software v17 | Estado de dados | Uso |
|---|---|---|---|
| IBGE Localidades | conector ativo | depende da execução da pipeline | catálogo nacional de municípios |
| CAR | adaptador geoespacial configurável | **não presumido como ingerido** | registro ambiental rural |
| SIGEF | adaptador configurável/credenciado | **não presumido como ingerido** | georreferenciamento certificado |
| IBAMA Embargos | CKAN/SHP-ZIP/GDAL suportado | **não presumido como ingerido** | restrição administrativa espacial |
| PRODES/INPE | WFS/GeoJSON configurável | **não presumido como ingerido** | monitoramento temporal |
| SNCR/CCIR | domínio/modelo pronto | conector/autorização ainda necessários | cadastro rural INCRA |
| CIB/CAFIR | domínio/modelo pronto | conector/autorização ainda necessários | identificação fiscal |
| SICOR | domínio/modelo pronto | ingestão específica ainda necessária | crédito rural analítico |
| FUNAI TI | catálogo de layer pronto | ingestão oficial ainda necessária | restrição/contexto territorial |
| CNUC | catálogo de layer pronto | ingestão oficial ainda necessária | unidades de conservação |

A v17 não semeia ocorrências fictícias para essas fontes. Ausência de snapshot significa `NOT_AVAILABLE`, nunca “não há ocorrência”.
