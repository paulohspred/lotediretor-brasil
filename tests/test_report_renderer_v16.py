from pathlib import Path
import sys, hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'workers/reports'))
from renderer import render_structured
from builder import canonical_json

doc={
 'schemaVersion':'report-360-v1',
 'template':{'code':'PROPERTY360_360','version':1,'title':'LoteDiretor Brasil — Ficha 360'},
 'report':{'id':'00000000-0000-0000-0000-000000000001'},
 'analysis':{'base_date':'2026-08-22','status':'COMPLETED'},
 'confidenceSummary':{'confirmed':2,'calculated':1,'not_available':1},
 'sections':[
  {'code':'cover','ordinal':1,'title':'Capa e identificação','status':'CONFIRMED','summary':'Identificação','payload':{'parcel':{'municipality_ibge':'3550308','official_identifier':'TESTE','area_m2':500,'geometry':{'type':'Polygon','coordinates':[[[-46.64,-23.55],[-46.63,-23.55],[-46.63,-23.54],[-46.64,-23.54],[-46.64,-23.55]]]}}}},
  {'code':'parameters','ordinal':2,'title':'Parâmetros urbanísticos','status':'CONFIRMED','summary':'Regras','payload':{'parameters':[{'parameter':'CA_MAX','value_numeric':4,'unit':'ratio','status':'CONFIRMED','source_locator':'Quadro 3'}]}},
  {'code':'potential','ordinal':3,'title':'Potencial','status':'CALCULATED','summary':'Cálculo','payload':{'calculations':[{'code':'POTENTIAL_MAX_M2','value_numeric':2000,'unit':'m²','formula':'area × CA','status':'CALCULATED'}]}},
  {'code':'risk','ordinal':4,'title':'Risco','status':'NOT_AVAILABLE','summary':'Sem camada','payload':{'relations':[]}},
 ],
 'disclaimers':['Não substitui certidão oficial.']
}
pdf=render_structured(doc)
assert pdf.startswith(b'%PDF')
assert len(pdf)>2500
raw=canonical_json(doc)
assert b'report-360-v1' in raw
assert len(hashlib.sha256(pdf).hexdigest())==64
print('v16 structured report renderer OK',len(pdf))
