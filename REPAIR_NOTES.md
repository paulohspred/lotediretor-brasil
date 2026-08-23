# Repair notes — v19-rc.3

A RC3 é cumulativa sobre a RC2. As mudanças foram tratadas como correções de produto/arquitetura, não como alteração cosmética de versão.

## Reparos relevantes

- A.I TEC deixa de depender apenas de massing + parking e ganha acesso/road conceitual, locks/branch, program gate, terreno por amostras, Building Stack e exports;
- locks preservam a geometria válida original em vez de aplicar transformação desnecessária antes do branch;
- área impermeável usa união geométrica de edifícios, parking e road para evitar dupla contagem;
- acesso não é inferido: sem `access_point` explícito, o solver não inventa rua/frente;
- `solar.regulation_snapshot` passa a ter unicidade correta para linhas globais com `tenant_id IS NULL` via índices parciais;
- Solar electrical solver não possui defaults comerciais fictícios: exige datasheet elétrico explícito;
- A.I TEC ganha FKs compostas por tenant e tabela `analysis_result` com RLS/FORCE RLS;
- artefatos A.I TEC podem pertencer a cenário legado ou a solution RC, com constraint de exclusividade;
- ferramenta de inspeção municipal deixa de exigir DB/psycopg para operações somente HTTP;
- `connectors.py` não exige mais `PLATFORM_DATABASE_URL` no import; comandos de persistência falham explicitamente quando DB não está configurado;
- user-agent de conectores atualizado para a RC3;
- falhas CLI de município retornam JSON operacional em stderr.

## Limites deliberados

Nenhuma migration RC3 foi marcada como runtime-PASS sem PostgreSQL/PostGIS. Nenhuma fonte GeoSampa foi marcada como ingerida sem rede. Nenhum `package-lock.json` foi criado manualmente. Nenhum output Solar/A.I TEC é rotulado como projeto executivo.
