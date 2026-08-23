# Foundation v0.1

A Seção 32 do Blueprint Final v2.0 prevalece. Esta release implementa a fundação do monorepo, Control/Data Plane separados, OIDC BFF, schemas, UI shells e motores especializados desacoplados.

## Regra de evolução
Nenhum novo módulo pode acessar tabela de outro bounded context diretamente. Use service/repository/event contract.
