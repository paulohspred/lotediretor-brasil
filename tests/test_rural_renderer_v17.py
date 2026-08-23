import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'workers'/'reports'))
from renderer import render_structured

doc={'schemaVersion':'rural-360-v1','template':{'code':'RURAL360_360','version':1,'title':'RE Rural 360'},'report':{'id':'r1','base_date':'2026-08-22'},'analysis':{'base_date':'2026-08-22','status':'RURAL_DOSSIER'},'confidenceSummary':{'confirmed':2,'calculated':2,'pending':1},'sections':[
 {'code':'rural_cover','ordinal':1,'title':'Ativo','status':'CONFIRMED','summary':'Ativo interno','payload':{'asset':{'name':'Fazenda Teste','municipality_ibge':'3550308','area_m2':10000,'geometry':{'type':'Polygon','coordinates':[[[-46,-23],[-45.99,-23],[-45.99,-22.99],[-46,-22.99],[-46,-23]]]}}}},
 {'code':'rural_identity','ordinal':2,'title':'Identidade','status':'INFERRED','summary':'candidato','payload':{'links':[{'relationship':'SAME_PHYSICAL_AREA_CANDIDATE','confidence':0.8,'status':'CANDIDATE','reasons':[{'code':'GEOMETRY_OVERLAP'}]}],'identifiers':[{'identifier_type':'CAR','identifier_value':'X','status':'OBSERVED'}]}},
 {'code':'rural_registries','ordinal':3,'title':'Registros','status':'CONFIRMED','summary':'fontes','payload':{'records':[{'registry_type':'CAR','official_identifier':'X','authority':'SICAR','validation_status':'PASS','area_m2':10000}]}},
 {'code':'rural_environment','ordinal':4,'title':'Ambiental','status':'CALCULATED','summary':'overlap','payload':{'layerHits':[{'code':'IBAMA_EMBARGO','authority':'IBAMA','official_identifier':'E1','intersection_area_m2':20,'intersection_ratio':0.002}]}},
 {'code':'rural_monitoring','ordinal':5,'title':'Monitoramento','status':'CALCULATED','summary':'monitor','payload':{'monitors':[{'monitor_type':'SOURCE_CHANGE','status':'ACTIVE','event_count':0}],'events':[]}},
 {'code':'rural_evidence','ordinal':6,'title':'Evidências','status':'CONFIRMED','summary':'hashes','payload':{'evidence':[{'evidenceType':'SOURCE_SNAPSHOT','sourceCode':'CAR','sha256':'a'*64,'confidenceStatus':'CONFIRMED'}],'exports':[]}},
 {'code':'rural_limitations','ordinal':7,'title':'Limitações','status':'PENDING','summary':'limites','payload':{'limitations':['CAR não prova domínio.']}}
],'disclaimers':['Não substitui certidões oficiais.']}
pdf=render_structured(doc)
assert pdf.startswith(b'%PDF') and len(pdf)>3000
print('rural renderer v17 OK',len(pdf))
