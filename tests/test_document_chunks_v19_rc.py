import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'workers'/'documents'))
from chunking import semantic_chunks

text='''<<<PAGE:1>>>
Art. 1º Primeira regra.\n\nParágrafo independente com condição.\n\n''' + ('Texto longo. '*220) + '''\n<<<PAGE:2>>>
Art. 2º Segunda regra.\n\nOutro parágrafo.'''
chunks=semantic_chunks(text,size=500,overlap=50)
assert chunks
assert chunks[0]['page_number']==1
assert any(x['page_number']==2 for x in chunks)
assert all(x['locator'].startswith(f"page:{x['page_number']}#chunk-") for x in chunks)
assert all(len(x['text'])<=500 for x in chunks)
assert any('Primeira regra.\n\nParágrafo independente' in x['text'] for x in chunks)
# Long paragraph should use overlapping windows rather than truncation.
long=[x for x in chunks if x['page_number']==1 and 'Texto longo.' in x['text']]
assert len(long)>2
print('v19-rc page-aware semantic chunking OK',len(chunks))
