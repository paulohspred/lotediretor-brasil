import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'workers'/'reports'))
from renderer import render_structured
condo={'schemaVersion':'condo-360-v1','template':{'code':'CONDO360_360','version':1,'title':'Condomínio 360'},'report':{'id':'c1','base_date':'2026-08-22'},'analysis':{'status':'CONDO_DOSSIER'},'confidenceSummary':{'confirmed':3,'calculated':2,'pending':1},'sections':[
 {'code':'condo_cover','ordinal':1,'title':'Condomínio','status':'CONFIRMED','summary':'id','payload':{'condominium':{'name':'Residencial Teste','kind':'VERTICAL','municipality_ibge':'3550308'}}},
 {'code':'condo_rules','ordinal':2,'title':'Regras','status':'CONFIRMED','summary':'rules','payload':{'rules':[{'rule_type':'PROHIBITION','title':'Fachada','status':'CONFIRMED','source_locator':'p. 12'}]}},
 {'code':'condo_units','ordinal':3,'title':'Unidades','status':'CONFIRMED','summary':'units','payload':{'buildings':[{'code':'A','name':'Bloco A','floors':10}],'units':[{'building_code':'A','code':'101','kind':'UNIT','private_area_m2':80,'status':'ACTIVE'}],'commonAreas':[]}},
 {'code':'condo_works','ordinal':4,'title':'Obras','status':'CALCULATED','summary':'works','payload':{'works':[{'title':'Reforma','work_type':'REFORM','status':'SUBMITTED'}]}},
 {'code':'condo_limitations','ordinal':5,'title':'Limitações','status':'PENDING','summary':'lim','payload':{'limitations':['Revisão humana obrigatória.']}}
],'disclaimers':['Não substitui assessoria.']}
solar={'schemaVersion':'solar-360-v1','template':{'code':'SOLAR360_360','version':1,'title':'Energia Solar 360'},'report':{'id':'s1','base_date':'2026-08-22'},'analysis':{'status':'SOLAR_PRELIMINARY_STUDY'},'confidenceSummary':{'confirmed':1,'calculated':4,'pending':2},'sections':[
 {'code':'solar_cover','ordinal':1,'title':'Projeto','status':'CONFIRMED','summary':'id','payload':{'project':{'name':'Solar Teste','status':'DRAFT'}}},
 {'code':'solar_surfaces','ordinal':2,'title':'Superfícies','status':'CALCULATED','summary':'surface','payload':{'surfaces':[{'code':'R1','kind':'ROOF','area_m2':100,'pitch_deg':10,'azimuth_deg':0,'usable_fraction':.9,'confidence_status':'PENDING'}],'obstacles':[]}},
 {'code':'solar_layout','ordinal':3,'title':'Layout','status':'CALCULATED','summary':'layout','payload':{'layouts':[{'name':'L1','status':'PRELIMINARY','module_code':'DEMO-MOD-550','panel_count':30,'dc_kwp':16.5,'engine_version':'18.0.0'}]}},
 {'code':'solar_consumption','ordinal':4,'title':'Consumo','status':'CALCULATED','summary':'energy','payload':{'bills':[{'reference_month':'2026-01-01','consumption_kwh':800,'origin':'USER_ENTERED'}],'balances':[]}},
 {'code':'solar_limitations','ordinal':5,'title':'Limitações','status':'PENDING','summary':'lim','payload':{'limitations':['Estudo preliminar.']}}
],'disclaimers':['Não substitui projeto executivo.']}
for d in (condo,solar):
 pdf=render_structured(d);assert pdf.startswith(b'%PDF') and len(pdf)>2500
print('v18 condo+solar report renderers OK')
