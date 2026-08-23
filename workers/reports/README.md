# Report Worker — v18

O worker v18 gera dois contratos estruturados sobre o mesmo motor de snapshot/evidência:

- `PROPERTY360_360` a partir de `analysis.run`;
- `RURAL360_360` a partir de `rural.asset` privado do tenant.

Cada execução congela `report.snapshot`, `report.section` e `report.evidence`, gera PDF + manifesto JSON no object storage, calcula SHA-256 e publica `report.completed` pelo outbox.

O Rural 360 preserva CAR, SNCR/CCIR, SIGEF, CIB, matrícula de referência, embargo, PRODES e SICOR como naturezas distintas; links automáticos permanecem candidatos até revisão.

Ainda pendente para versões posteriores: DOCX, mapa cartográfico com basemap/legenda e assinatura profissional/ART.
