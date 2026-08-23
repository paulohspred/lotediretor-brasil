import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'workers'/'documents'))
from rules import condo_candidates
text='''
CAPÍTULO V - DAS OBRIGAÇÕES
É proibida a instalação de equipamentos na fachada sem aprovação do condomínio.
A instalação de ar-condicionado poderá ocorrer mediante aprovação técnica.
O quórum para alteração desta regra será de dois terços dos condôminos.
Piscina
'''
r=condo_candidates(text)
assert len(r)>=3,r
assert all(x['confidence']<1 for x in r)
assert {x['rule_type'] for x in r}>={'PROHIBITION','PERMISSION','QUORUM'}
assert all(x['source_locator'].startswith('line:') for x in r)
print('condo deterministic candidates v18 OK',len(r))
