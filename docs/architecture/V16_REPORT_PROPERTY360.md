# v16 — Report Engine e Imóvel 360

## Fluxo

`analysis.run` congelado → `report.report_run` → Report Worker → `report.snapshot` + `report.section` + `report.evidence` → PDF + JSON no object storage → `report.completed`.

## Invariantes

- O relatório nunca consulta uma fonte externa diretamente.
- Todo dado exibido vem do estado persistido/snapshot da análise.
- Seção sem fonte não recebe confirmação.
- Regras jurídicas carregam document_version/localizador/hash quando disponíveis.
- Relações espaciais carregam source_snapshot_id.
- O manifesto JSON é canônico e hashável.
- Compartilhamento armazena apenas hash do token; resolução pública permanece desativada até security gate específico.

## Ficha 360

A Ficha 360 passa a ser um objeto persistido (`property360.property`) ligado a Analysis Runs. O agregado de ficha reúne análises, AVM, notas, diligências, CRM e relatórios sem duplicar as fontes técnicas.
