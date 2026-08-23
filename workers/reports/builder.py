from __future__ import annotations
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Any
import json

SECTION_DOMAIN = {
    'environment': {'ENVIRONMENT'},
    'risk': {'RISK'},
    'infrastructure': {'INFRA'},
    'mobility': {'MOBILITY'},
    'heritage': {'HERITAGE'},
    'licensing': {'LICENSING'},
}

def primitive(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): primitive(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [primitive(v) for v in value]
    return value


def rows(cur) -> list[dict[str, Any]]:
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def one(cur) -> dict[str, Any] | None:
    cols = [d.name for d in cur.description]
    row = cur.fetchone()
    return dict(zip(cols, row)) if row else None


def status_for(items: list[dict[str, Any]], default='NOT_AVAILABLE') -> str:
    if not items:
        return default
    statuses = {str(x.get('status') or '').upper() for x in items}
    if 'CONFLICTING' in statuses or 'CONFLITANTE' in statuses:
        return 'CONFLICTING'
    if 'INFERRED' in statuses or 'INFERIDO' in statuses:
        return 'INFERRED'
    if 'PENDING' in statuses or 'PENDENTE' in statuses:
        return 'PENDING'
    if 'CALCULATED' in statuses or 'CALCULADO' in statuses:
        return 'CALCULATED'
    return 'CONFIRMED'


def build_analysis_report(conn, tenant_id: str, report_run: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    run_id = report_run['subject_id']
    analysis = one(conn.execute(
        "select id,tenant_id,property_id,status,base_date,input_snapshot,created_at from analysis.run where id=%s and tenant_id=%s",
        (run_id, tenant_id),
    ))
    if not analysis:
        raise ValueError('analysis_not_found')

    parcel_id = (analysis.get('input_snapshot') or {}).get('resolvedParcelId')
    parcel = None
    if parcel_id:
        parcel = one(conn.execute(
            """select p.id,p.official_identifier,p.municipality_ibge,p.source_snapshot_id,
                      st_area(p.geom::geography) area_m2,st_perimeter(p.geom::geography) perimeter_m,
                      st_y(st_centroid(p.geom)) centroid_lat,st_x(st_centroid(p.geom)) centroid_lon,
                      st_asgeojson(p.geom)::jsonb geometry,p.valid_from,p.valid_to
                 from geo.parcel p where p.id=%s and (p.tenant_id is null or p.tenant_id=%s)""",
            (parcel_id, tenant_id),
        ))

    parameters = rows(conn.execute(
        """select ap.parameter,ap.value_numeric,ap.value_text,ap.unit,ap.status,ap.rule_id,
                  ap.source_document_version_id,ap.source_locator,d.title document_title,
                  dv.version_label,dv.effective_date,dv.sha256 document_sha256
             from planning.analysis_parameter ap
             left join legal.document_version dv on dv.id=ap.source_document_version_id
             left join legal.document d on d.id=dv.document_id
            where ap.run_id=%s order by ap.parameter""", (run_id,)
    ))
    calculations = rows(conn.execute(
        "select code,value_numeric,value_text,unit,formula,inputs,rule_ids,status from analysis.calculation where run_id=%s order by code",
        (run_id,),
    ))
    findings = rows(conn.execute(
        "select id,category,status,code,title,value,evidence_ids,created_at from analysis.finding where run_id=%s order by category,created_at",
        (run_id,),
    ))
    spatial = rows(conn.execute(
        """select sr.relation_type,sr.layer_code,l.title layer_title,l.domain,sr.feature_id,
                  sr.distance_m,sr.intersection_area_m2,sr.intersection_ratio,sr.source_snapshot_id,
                  sr.evidence
             from analysis.spatial_relation sr
             left join geo.layer l on l.code=sr.layer_code
            where sr.run_id=%s order by l.domain,sr.layer_code""", (run_id,)
    ))
    snapshots = rows(conn.execute(
        """select ar.purpose,s.id snapshot_id,s.sha256,s.source_date,s.ingested_at,s.parser_version,
                  s.validation_status,s.status snapshot_status,s.object_key,r.code source_code,r.title source_title,
                  r.authority,r.base_url,r.license_terms
             from analysis.snapshot_ref ar join source.snapshot s on s.id=ar.source_snapshot_id
             join source.registry r on r.id=s.source_id where ar.run_id=%s order by r.code""", (run_id,)
    ))
    conflicts = []
    municipality = parcel.get('municipality_ibge') if parcel else (analysis.get('input_snapshot') or {}).get('municipalityIbge')
    zone_code = (analysis.get('input_snapshot') or {}).get('zoneCode')
    if municipality:
        conflicts = rows(conn.execute(
            "select id,zone_code,parameter,rule_ids,status,reason,resolution,created_at from legal.conflict where municipality_ibge=%s and (%s::text is null or zone_code=%s) and status='OPEN' order by created_at",
            (municipality, zone_code, zone_code),
        ))

    property_row = None
    if analysis.get('property_id'):
        property_row = one(conn.execute(
            "select id,name,address,municipality_ibge,status,tags,attributes,created_at,updated_at from property360.property where id=%s and tenant_id=%s",
            (analysis['property_id'], tenant_id),
        ))

    notes: list[dict[str, Any]] = []
    diligences: list[dict[str, Any]] = []
    avms: list[dict[str, Any]] = []
    if property_row:
        notes = rows(conn.execute(
            "select id,body,tags,created_by,created_at from property360.property_note where property_id=%s and tenant_id=%s order by created_at desc limit 100",
            (property_row['id'], tenant_id),
        ))
        diligences = rows(conn.execute(
            "select id,title,description,status,priority,owner_user_id,due_at,completed_at,evidence,created_at from property360.diligence where property_id=%s and tenant_id=%s order by created_at desc",
            (property_row['id'], tenant_id),
        ))
        avms = rows(conn.execute(
            "select id,municipality_ibge,area_m2,model_version,status,estimate_cents,confidence,assumptions,created_at from property360.avm_run where property_id=%s and tenant_id=%s order by created_at desc limit 20",
            (property_row['id'], tenant_id),
        ))

    by_domain: dict[str, list[dict[str, Any]]] = {}
    for item in spatial:
        by_domain.setdefault(str(item.get('domain') or 'OTHER').upper(), []).append(item)

    param_map = {str(p['parameter']).upper(): p for p in parameters}
    calc_map = {str(c['code']).upper(): c for c in calculations}
    critical = []
    for p in parameters[:20]:
        critical.append({'kind':'PARAMETER','code':p['parameter'],'value':p['value_numeric'] if p['value_numeric'] is not None else p['value_text'],'unit':p['unit'],'status':p['status']})
    for f in findings[:20]:
        if str(f.get('category') or '').upper() != 'URBAN_RULE':
            critical.append({'kind':'FINDING','code':f.get('code'),'title':f.get('title'),'status':f.get('status')})

    section_payloads: dict[str, dict[str, Any]] = {}
    section_payloads['cover'] = {
        'status':'CONFIRMED' if parcel else 'PENDING',
        'summary':'Identificação da análise e coordenada temporal.',
        'data':{'reportId':report_run['id'],'analysisId':run_id,'baseDate':analysis['base_date'],'property':property_row,'parcel':parcel},
    }
    section_payloads['executive'] = {
        'status':'CONFLICTING' if conflicts else ('CONFIRMED' if critical else 'PENDING'),
        'summary':f"{len(parameters)} parâmetros, {len(calculations)} cálculos, {len(spatial)} relações espaciais e {len(conflicts)} conflitos abertos.",
        'data':{'critical':critical[:20],'limitations':[] if critical else ['Nenhuma conclusão técnica confirmada disponível.'],'conflicts':conflicts},
    }
    section_payloads['identification'] = {
        'status':'CONFIRMED' if parcel else 'NOT_AVAILABLE',
        'summary':'Lote, município, geometria, área e identificadores disponíveis.',
        'data':{'parcel':parcel,'property':property_row},
    }
    section_payloads['map'] = {
        'status':'CALCULATED' if parcel and parcel.get('geometry') else 'NOT_AVAILABLE',
        'summary':'Geometria reproduzível do lote usada pela análise.',
        'data':{'geometry':parcel.get('geometry') if parcel else None,'centroid':{'lat':parcel.get('centroid_lat'),'lon':parcel.get('centroid_lon')} if parcel else None},
    }
    section_payloads['urban'] = {
        'status':'CONFLICTING' if conflicts else status_for(parameters),
        'summary':f"Zona {zone_code or 'não identificada'}; regras vigentes preservam documento, versão e localizador.",
        'data':{'municipalityIbge':municipality,'zoneCode':zone_code,'parameters':parameters,'conflicts':conflicts},
    }
    use_params = [p for p in parameters if str(p['parameter']).upper().startswith(('USE_','USO_'))]
    section_payloads['uses'] = {
        'status':status_for(use_params),
        'summary':'Classificação de usos depende de regras estruturadas específicas do município.',
        'data':{'rules':use_params},
    }
    section_payloads['parameters'] = {
        'status':status_for(parameters),
        'summary':'Parâmetros urbanísticos confirmados na data-base.',
        'data':{'parameters':parameters},
    }
    section_payloads['potential'] = {
        'status':'CALCULATED' if calculations else 'NOT_AVAILABLE',
        'summary':'Cálculos reproduzíveis, sem confundir potencial teórico com área vendável.',
        'data':{'calculations':calculations},
    }
    instrument_params = [p for p in parameters if any(k in str(p['parameter']).upper() for k in ('OUTORGA','CEPAC','TDC','PEUC'))]
    section_payloads['instruments'] = {'status':status_for(instrument_params),'summary':'Instrumentos urbanísticos identificados nas regras publicadas.','data':{'rules':instrument_params}}

    for section, domains in SECTION_DOMAIN.items():
        items = [x for d in domains for x in by_domain.get(d, [])]
        title = section
        section_payloads[section] = {
            'status':'CONFIRMED' if items else 'NOT_AVAILABLE',
            'summary':f"{len(items)} relação(ões) espacial(is) confirmada(s) em camada publicada." if items else 'Nenhuma camada publicada disponível/intersectante nesta categoria.',
            'data':{'relations':items},
        }

    section_payloads['linear'] = {
        'status':'NOT_AVAILABLE',
        'summary':'Mineração, dutos, ferrovias, rodovias e portos dependem de camadas oficiais ainda não presentes neste Analysis Run.',
        'data':{},
    }
    section_payloads['amenities'] = {
        'status':'NOT_AVAILABLE',
        'summary':'Equipamentos e análise de entorno exigem dados de proximidade publicados para o município.',
        'data':{},
    }
    section_payloads['fiscal_market'] = {
        'status':'CALCULATED' if avms else 'NOT_AVAILABLE',
        'summary':'Cadastro/mercado só é exibido quando há fonte e classe de dado identificadas.',
        'data':{'avmRuns':avms},
    }
    section_payloads['diligence'] = {
        'status':'PENDING' if any(d.get('status') not in ('DONE','CLOSED') for d in diligences) else ('CONFIRMED' if diligences else 'NOT_AVAILABLE'),
        'summary':f"{len(diligences)} diligência(s) registrada(s).",
        'data':{'diligences':diligences,'notes':notes},
    }
    section_payloads['evidence'] = {
        'status':'CONFIRMED' if snapshots or parameters or spatial else 'NOT_AVAILABLE',
        'summary':f"{len(snapshots)} snapshot(s), {len(parameters)} regra(s)/parâmetro(s) e {len(spatial)} relação(ões) espacial(is).",
        'data':{'snapshots':snapshots,'parameters':parameters,'spatial':spatial},
    }

    configured_sections = template.get('section_order') or []
    sections: list[dict[str, Any]] = []
    for idx, configured in enumerate(configured_sections, start=1):
        code = configured['code']
        payload = section_payloads.get(code, {'status':'NOT_AVAILABLE','summary':'Seção sem dados estruturados disponíveis.','data':{}})
        sections.append({'code':code,'ordinal':idx,'title':configured['title'],'status':payload['status'],'summary':payload['summary'],'payload':payload['data']})

    evidence: list[dict[str, Any]] = []
    for s in snapshots:
        evidence.append({'sectionCode':'evidence','evidenceType':'SOURCE_SNAPSHOT','sourceCode':s.get('source_code'),'sourceSnapshotId':s.get('snapshot_id'),'sha256':s.get('sha256'),'confidenceStatus':'CONFIRMED' if s.get('validation_status') == 'PASS' else 'PENDING','payload':s})
    for p in parameters:
        evidence.append({'sectionCode':'parameters','evidenceType':'LEGAL_RULE','sourceDocumentVersionId':p.get('source_document_version_id'),'sourceLocator':p.get('source_locator'),'sha256':p.get('document_sha256'),'confidenceStatus':p.get('status') or 'CONFIRMED','payload':{'parameter':p.get('parameter'),'documentTitle':p.get('document_title'),'versionLabel':p.get('version_label')}})
    for rel in spatial:
        evidence.append({'sectionCode':next((k for k,v in SECTION_DOMAIN.items() if str(rel.get('domain') or '').upper() in v),'evidence'),'evidenceType':'SPATIAL_RELATION','sourceSnapshotId':rel.get('source_snapshot_id'),'confidenceStatus':'CONFIRMED','payload':rel})

    counts = Counter(x['status'] for x in sections)
    confidence = {k.lower(): v for k, v in counts.items()}
    confidence['totalSections'] = len(sections)

    doc = {
        'schemaVersion':'report-360-v1',
        'template':{'code':template['code'],'version':template['version'],'title':template['title']},
        'report':report_run,
        'analysis':analysis,
        'property':property_row,
        'parcel':parcel,
        'sections':sections,
        'evidence':evidence,
        'confidenceSummary':confidence,
        'disclaimers':[
            'Relatório de inteligência técnica; não substitui certidão oficial, consulta formal ou responsabilidade técnica quando exigida.',
            'Ausência de fonte publicada é apresentada como NOT_AVAILABLE/PENDING e nunca convertida em confirmação.',
            'Potencial urbanístico máximo não equivale automaticamente a área vendável ou garantia de aprovação.'
        ],
    }
    return primitive(doc)



def build_rural_report(conn, tenant_id: str, report_run: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    asset_id = report_run['subject_id']
    base_date = report_run['base_date']
    asset = one(conn.execute("""select id,name,municipality_ibge,created_at,
        case when geom is null then null else st_area(geom::geography) end area_m2,
        case when geom is null then null else st_asgeojson(geom)::jsonb end geometry
        from rural.asset where id=%s and tenant_id=%s""", (asset_id, tenant_id)))
    if not asset:
        raise ValueError('rural_asset_not_found')

    records = rows(conn.execute("""select rr.id,rr.registry_type,rr.official_identifier,rr.valid_from,rr.valid_to,
        rr.source_snapshot_id,s.sha256 source_sha256,s.source_date,s.validation_status,s.status snapshot_status,
        sr.code source_code,sr.authority,sr.base_url,sr.license_terms,
        case when rr.geom is null then null else st_area(rr.geom::geography) end area_m2
        from rural.registry_record rr
        left join source.snapshot s on s.id=rr.source_snapshot_id
        left join source.registry sr on sr.id=s.source_id
        where rr.asset_id=%s
          and (rr.valid_from is null or rr.valid_from <= %s::date + interval '1 day')
          and (rr.valid_to is null or rr.valid_to > %s::date)
        order by rr.registry_type,rr.valid_from desc nulls last""", (asset_id, base_date, base_date)))

    identifiers = rows(conn.execute("""select registry_record_id,identifier_type,
        case when identifier_type in ('CPF','CNPJ') then '[RESTRICTED]' else identifier_value end identifier_value,
        status,source_snapshot_id,valid_from,valid_to
        from rural.registry_identifier where asset_id=%s
          and (valid_from is null or valid_from <= %s::date + interval '1 day')
          and (valid_to is null or valid_to > %s::date)
        order by identifier_type""", (asset_id, base_date, base_date)))

    links = rows(conn.execute("""select id,left_record_id,right_record_id,relationship,confidence,status,reasons,reviewed_by,reviewed_at
        from rural.identity_link where asset_id=%s order by confidence desc""", (asset_id,)))

    overlaps = rows(conn.execute("""select rr.id registry_record_id,rr.registry_type overlap_type,rr.source_snapshot_id,
        st_area(st_intersection(a.geom,rr.geom)::geography) overlap_area_m2,
        case when st_area(a.geom::geography)>0 then st_area(st_intersection(a.geom,rr.geom)::geography)/st_area(a.geom::geography) end overlap_ratio,
        jsonb_build_object('official_identifier',rr.official_identifier,'source_snapshot_id',rr.source_snapshot_id,'source_kind','REGISTRY_RECORD') metadata
        from rural.asset a join rural.registry_record rr on rr.asset_id=a.id and rr.geom is not null and st_intersects(a.geom,rr.geom)
        where a.id=%s and a.tenant_id=%s
          and (rr.valid_from is null or rr.valid_from <= %s::date + interval '1 day')
          and (rr.valid_to is null or rr.valid_to > %s::date)
        order by rr.registry_type""", (asset_id, tenant_id, base_date, base_date)))

    monitors = rows(conn.execute("""select m.id,m.monitor_type,m.status,m.last_checked_at,m.last_change_at,m.configuration,m.created_at,
        (select count(*) from rural.monitor_event e where e.monitor_id=m.id and e.detected_at < %s::date + interval '1 day') event_count,
        (select state_hash from rural.monitor_checkpoint cp where cp.monitor_id=m.id and cp.checked_at < %s::date + interval '1 day' order by checked_at desc limit 1) state_hash
        from rural.monitor m where m.asset_id=%s and m.tenant_id=%s and m.created_at < %s::date + interval '1 day' order by m.created_at""",
        (base_date, base_date, asset_id, tenant_id, base_date)))
    events = rows(conn.execute("""select e.monitor_id,e.event_type,e.status,e.before_snapshot_id,e.after_snapshot_id,e.change_summary,e.detected_at
        from rural.monitor_event e join rural.monitor m on m.id=e.monitor_id
        where m.asset_id=%s and e.tenant_id=%s and e.detected_at < %s::date + interval '1 day'
        order by e.detected_at desc limit 100""", (asset_id, tenant_id, base_date)))

    layer_hits = rows(conn.execute("""with historical_snapshot as (
          select distinct on (s.source_id) s.id,s.source_id,s.sha256,s.source_date,s.ingested_at,s.validation_status,s.status
          from source.snapshot s
          where (s.validation_status='PASS' or s.status in ('VALIDATED','PUBLISHED'))
            and coalesce(s.source_date::date,s.ingested_at::date) <= %s::date
          order by s.source_id,coalesce(s.source_date,s.ingested_at) desc,s.ingested_at desc
        )
        select lc.code,lc.title,lc.authority,lf.official_identifier,lf.source_snapshot_id,
          hs.sha256 source_sha256,hs.source_date,hs.validation_status,hs.status snapshot_status,
          sr.base_url,sr.license_terms,
          st_area(st_intersection(a.geom,lf.geom)::geography) intersection_area_m2,
          case when st_area(a.geom::geography)>0 then st_area(st_intersection(a.geom,lf.geom)::geography)/st_area(a.geom::geography) end intersection_ratio
        from rural.asset a
        join rural.layer_feature lf on a.geom is not null and st_intersects(a.geom,lf.geom)
        join rural.layer_catalog lc on lc.code=lf.layer_code
        join historical_snapshot hs on hs.id=lf.source_snapshot_id
        join source.snapshot ss on ss.id=lf.source_snapshot_id
        join source.registry sr on sr.id=ss.source_id
        where a.id=%s and a.tenant_id=%s
          and (lf.valid_from is null or lf.valid_from <= %s::date + interval '1 day')
          and (lf.valid_to is null or lf.valid_to > %s::date)
        order by lc.code""", (base_date, asset_id, tenant_id, base_date, base_date)))

    exports = rows(conn.execute("""select id,format,status,object_key,sha256,size_bytes,created_at,completed_at
        from rural.export_job where asset_id=%s and tenant_id=%s and created_at < %s::date + interval '1 day'
        order by created_at desc limit 50""", (asset_id, tenant_id, base_date)))

    evidence=[]
    seen=set()
    for rec in records:
        sid=rec.get('source_snapshot_id')
        if sid and sid not in seen:
            seen.add(sid)
            evidence.append({'sectionCode':'rural_evidence','evidenceType':'SOURCE_SNAPSHOT','sourceCode':rec.get('source_code'),'sourceSnapshotId':sid,'sha256':rec.get('source_sha256'),'url':rec.get('base_url'),'confidenceStatus':'CONFIRMED' if rec.get('validation_status')=='PASS' else 'PENDING','payload':{'authority':rec.get('authority'),'sourceDate':rec.get('source_date'),'licenseTerms':rec.get('license_terms')}})
    for hit in layer_hits:
        sid=hit.get('source_snapshot_id')
        if sid and sid not in seen:
            seen.add(sid)
            evidence.append({'sectionCode':'rural_environment','evidenceType':'SOURCE_SNAPSHOT','sourceCode':hit.get('code'),'sourceSnapshotId':sid,'sha256':hit.get('source_sha256'),'url':hit.get('base_url'),'confidenceStatus':'CONFIRMED' if hit.get('validation_status')=='PASS' else 'PENDING','payload':{'authority':hit.get('authority'),'sourceDate':hit.get('source_date'),'licenseTerms':hit.get('license_terms')}})

    validated_records=[r for r in records if r.get('validation_status')=='PASS']
    sicor=[r for r in records if r.get('registry_type')=='SICOR']
    sicor_validated=[r for r in sicor if r.get('validation_status')=='PASS']
    sections=[
      {'code':'rural_cover','ordinal':1,'title':'Identificação do ativo rural','status':'CONFIRMED' if asset.get('geometry') else 'PENDING','summary':'Entidade física interna; não substitui nenhum cadastro oficial.','payload':{'asset':asset}},
      {'code':'rural_identity','ordinal':2,'title':'Grafo de identidade rural','status':'CONFIRMED' if any(x.get('status')=='CONFIRMED' for x in links) else ('INFERRED' if links else 'PENDING'),'summary':'Convergências preservam a natureza jurídica de cada registro.','payload':{'links':links,'identifiers':identifiers}},
      {'code':'rural_registries','ordinal':3,'title':'CAR · SNCR/CCIR · SIGEF · CIB e referências','status':'CONFIRMED' if validated_records else ('PENDING' if records else 'NOT_AVAILABLE'),'summary':f'{len(records)} registros normalizados vinculados ao ativo; {len(validated_records)} apoiados por snapshot validado.','payload':{'records':records,'identifiers':identifiers}},
      {'code':'rural_convergence','ordinal':4,'title':'Convergências, divergências e sobreposições','status':'CALCULATED' if overlaps or links else 'NOT_AVAILABLE','summary':'Relações geométricas e cadastrais calculadas sem inferir domínio.','payload':{'links':links,'overlaps':overlaps}},
      {'code':'rural_environment','ordinal':5,'title':'Embargos, PRODES e camadas territoriais','status':'CALCULATED' if layer_hits else 'NOT_AVAILABLE','summary':f'{len(layer_hits)} interseções com snapshots válidos na data-base.','payload':{'layerHits':layer_hits}},
      {'code':'rural_monitoring','ordinal':6,'title':'Monitoramento e mudanças','status':'CALCULATED' if monitors else 'NOT_AVAILABLE','summary':f'{len(monitors)} monitores e {len(events)} eventos até a data-base.','payload':{'monitors':monitors,'events':events}},
      {'code':'rural_credit','ordinal':7,'title':'Crédito rural / SICOR','status':'CONFIRMED' if sicor_validated else ('PENDING' if sicor else 'NOT_AVAILABLE'),'summary':'SICOR é camada analítica de crédito e não cadastro dominial.','payload':{'records':sicor}},
      {'code':'rural_evidence','ordinal':8,'title':'Evidências e snapshots','status':'CONFIRMED' if evidence and all(x.get('confidenceStatus')=='CONFIRMED' for x in evidence) else ('PENDING' if evidence else 'NOT_AVAILABLE'),'summary':'Snapshots, hashes, licenças e autoridades das fontes utilizadas.','payload':{'evidence':evidence,'exports':exports}},
      {'code':'rural_limitations','ordinal':9,'title':'Limitações e diligências','status':'PENDING','summary':'Conclusões dependem da natureza, vigência e cobertura de cada fonte.','payload':{'limitations':['CAR é declaratório e não prova domínio.','SNCR/CCIR é cadastral e não substitui matrícula.','SIGEF certifica georreferenciamento e não prova titularidade isoladamente.','CIB/CAFIR é fiscal e não substitui registro imobiliário.','Embargo/PRODES representam fatos/restrições ambientais segundo a fonte e data-base.','A geometria canônica do ativo ainda não possui versionamento próprio nesta release; relatórios históricos registram essa limitação.','Campos pessoais permanecem sujeitos a base legal, finalidade e auditoria.']}}
    ]
    counts=Counter(x['status'] for x in sections)
    return primitive({'schemaVersion':'rural-360-v1','template':template,'report':{'id':report_run['id'],'kind':report_run['kind'],'base_date':base_date},'analysis':{'base_date':base_date,'status':'RURAL_DOSSIER'},'asset':asset,'confidenceSummary':{'confirmed':counts['CONFIRMED'],'calculated':counts['CALCULATED'],'inferred':counts['INFERRED'],'pending':counts['PENDING'],'conflicting':counts['CONFLICTING'],'not_available':counts['NOT_AVAILABLE']},'sections':sections,'evidence':evidence,'disclaimers':['RE Rural relaciona fontes sem apagar suas naturezas jurídicas.','O dossiê não substitui matrícula/certidão, CCIR, CAR, certificação SIGEF ou consulta formal ao órgão competente.','Dados pessoais/sensíveis exigem base legal, finalidade e perfil de acesso compatível.']})



def build_condo_report(conn, tenant_id: str, report_run: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    condo_id=report_run['subject_id']; base_date=str(report_run.get('base_date') or date.today())
    condo=one(conn.execute("select id,name,kind,municipality_ibge,created_at from condo.condominium where id=%s and tenant_id=%s",(condo_id,tenant_id)))
    if not condo: raise ValueError('condominium_not_found')
    documents=rows(conn.execute("select id,kind,title,sha256,processing_status,processed_at,created_at from condo.document where condominium_id=%s and tenant_id=%s order by created_at desc",(condo_id,tenant_id)))
    rules=rows(conn.execute("select id,rule_type,title,rule_text,status,source_locator,valid_from,valid_to,reviewed_by,reviewed_at,extraction_method,confidence from condo.rule where condominium_id=%s and tenant_id=%s and (valid_from is null or valid_from <= %s::date + interval '1 day') and (valid_to is null or valid_to > %s::date) order by status desc,title",(condo_id,tenant_id,base_date,base_date)))
    buildings=rows(conn.execute("select id,code,name,floors,metadata from condo.building where condominium_id=%s order by code",(condo_id,)))
    units=rows(conn.execute("select u.id,u.code,u.kind,u.floor_label,u.private_area_m2,u.fraction,u.status,b.code building_code from condo.unit u left join condo.building b on b.id=u.building_id where u.condominium_id=%s order by b.code nulls first,u.code",(condo_id,)))
    areas=rows(conn.execute("select id,code,name,kind,area_m2,usage_policy from condo.common_area where condominium_id=%s order by code",(condo_id,)))
    works=rows(conn.execute("select id,title,work_type,status,art_rrt_reference,technical_responsible,submitted_at,reviewed_at,decision_reason,evidence from condo.work_request where condominium_id=%s and created_at < %s::date + interval '1 day' order by created_at desc",(condo_id,base_date)))
    assemblies=rows(conn.execute("select id,kind,title,scheduled_at,held_at,status,quorum_rule,document_id,created_at from condo.assembly where condominium_id=%s and created_at < %s::date + interval '1 day' order by scheduled_at desc",(condo_id,base_date)))
    decisions=rows(conn.execute("select id,assembly_id,agenda_item_id,title,decision_text,status,effective_from,effective_to,generates_rule,generated_rule_id,source_locator,approved_at from condo.decision where condominium_id=%s and created_at < %s::date + interval '1 day' order by created_at desc",(condo_id,base_date)))
    votes=rows(conn.execute("select v.agenda_item_id,v.eligible_count,v.present_count,v.favorable_count,v.contrary_count,v.abstention_count,v.fraction_favorable,v.quorum_result,v.methodology,v.calculated_at from condo.vote_summary v join condo.agenda_item i on i.id=v.agenda_item_id join condo.assembly a on a.id=i.assembly_id where a.condominium_id=%s and v.calculated_at < %s::date + interval '1 day' order by v.calculated_at desc",(condo_id,base_date)))
    maintenance=rows(conn.execute("select id,system_code,title,interval_days,last_done_at,next_due_at,status,evidence from condo.maintenance_item where condominium_id=%s order by next_due_at nulls last",(condo_id,)))
    occurrences=rows(conn.execute("select id,category,title,status,severity,defense_due_at,resolution,closed_at,created_at from condo.occurrence where condominium_id=%s and created_at < %s::date + interval '1 day' order by created_at desc",(condo_id,base_date)))
    compliance=rows(conn.execute("select id,code,title,category,status,due_at,responsible,source_rule_id,evidence from condo.compliance_item where condominium_id=%s order by due_at nulls last",(condo_id,)))
    evidence=rows(conn.execute("select e.id,e.rule_id,e.document_id,e.chunk_id,e.locator,d.title document_title,d.sha256 document_sha256 from condo.evidence_link e left join condo.document d on d.id=e.document_id where e.condominium_id=%s and e.tenant_id=%s order by e.created_at",(condo_id,tenant_id)))
    confirmed=[r for r in rules if r.get('status')=='CONFIRMED']; candidates=[r for r in rules if r.get('status')=='CANDIDATE']
    sections=[
      {'code':'condo_cover','ordinal':1,'title':'Identificação do condomínio','status':'CONFIRMED','summary':'Workspace privado do condomínio.','payload':{'condominium':condo,'baseDate':base_date}},
      {'code':'condo_documents','ordinal':2,'title':'Biblioteca documental','status':'CONFIRMED' if documents else 'NOT_AVAILABLE','summary':f'{len(documents)} documentos; hashes preservam rastreabilidade.','payload':{'documents':documents}},
      {'code':'condo_rules','ordinal':3,'title':'Regras, vigência e revisão','status':'CONFIRMED' if confirmed else ('PENDING' if rules else 'NOT_AVAILABLE'),'summary':f'{len(confirmed)} regras confirmadas e {len(candidates)} candidatas na data-base.','payload':{'rules':rules}},
      {'code':'condo_units','ordinal':4,'title':'Blocos, unidades e áreas comuns','status':'CONFIRMED' if units or areas else 'NOT_AVAILABLE','summary':f'{len(buildings)} blocos, {len(units)} unidades e {len(areas)} áreas comuns.','payload':{'buildings':buildings,'units':units,'commonAreas':areas}},
      {'code':'condo_works','ordinal':5,'title':'Obras e reformas','status':'CALCULATED' if works else 'NOT_AVAILABLE','summary':f'{len(works)} solicitações registradas.','payload':{'works':works}},
      {'code':'condo_assemblies','ordinal':6,'title':'Assembleias, quóruns e deliberações','status':'CALCULATED' if assemblies or decisions else 'NOT_AVAILABLE','summary':f'{len(assemblies)} assembleias e {len(decisions)} decisões.','payload':{'assemblies':assemblies,'decisions':decisions,'voteSummaries':votes}},
      {'code':'condo_maintenance','ordinal':7,'title':'Manutenção e seguros/compliance operacional','status':'CALCULATED' if maintenance else 'NOT_AVAILABLE','summary':f'{len(maintenance)} itens de manutenção.','payload':{'maintenance':maintenance}},
      {'code':'condo_occurrences','ordinal':8,'title':'Ocorrências e tratamento humano','status':'CALCULATED' if occurrences else 'NOT_AVAILABLE','summary':f'{len(occurrences)} ocorrências; nenhuma sanção é aplicada automaticamente pela IA.','payload':{'occurrences':occurrences}},
      {'code':'condo_compliance','ordinal':9,'title':'Compliance e pendências','status':'CALCULATED' if compliance else 'NOT_AVAILABLE','summary':f'{len(compliance)} itens de compliance.','payload':{'compliance':compliance}},
      {'code':'condo_evidence','ordinal':10,'title':'Evidências e localizadores','status':'CONFIRMED' if evidence else 'NOT_AVAILABLE','summary':'Documentos, hashes, chunks e localizadores das regras.','payload':{'evidence':evidence}},
      {'code':'condo_limitations','ordinal':11,'title':'Limitações e orientação profissional','status':'PENDING','summary':'Regra interna, lei externa, deliberação e orientação profissional permanecem conceitos distintos.','payload':{'limitations':['Regras extraídas automaticamente permanecem CANDIDATE até revisão humana.','A.I Condomínio não aplica multa, advertência, boleto ou alteração cadastral sem ação explícita autorizada.','O relatório não substitui assessoria jurídica, técnica ou decisão assemblear quando exigidas.']}}
    ]
    counts=Counter(x['status'] for x in sections)
    return primitive({'schemaVersion':'condo-360-v1','template':template,'report':{'id':report_run['id'],'kind':report_run['kind'],'base_date':base_date},'analysis':{'base_date':base_date,'status':'CONDO_DOSSIER'},'condominium':condo,'confidenceSummary':{'confirmed':counts['CONFIRMED'],'calculated':counts['CALCULATED'],'inferred':counts['INFERRED'],'pending':counts['PENDING'],'conflicting':counts['CONFLICTING'],'not_available':counts['NOT_AVAILABLE']},'sections':sections,'evidence':evidence,'disclaimers':['Condomínio 360 organiza documentos e decisões; não substitui assessoria jurídica/técnica.','Dados privados permanecem isolados por tenant e finalidade.']})


def build_solar_report(conn, tenant_id: str, report_run: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    project_id=report_run['subject_id']; base_date=str(report_run.get('base_date') or date.today())
    project=one(conn.execute("select id,name,status,property_id,input_snapshot,created_at from solar.project where id=%s and tenant_id=%s",(project_id,tenant_id)))
    if not project: raise ValueError('solar_project_not_found')
    sites=rows(conn.execute("select id,kind,name,municipality_ibge,latitude,longitude,elevation_m,source_snapshot_id,data_quality,created_at from solar.site where project_id=%s order by created_at",(project_id,)))
    surfaces=rows(conn.execute("select sf.id,sf.site_id,sf.code,sf.kind,sf.local_frame,sf.area_m2,sf.pitch_deg,sf.azimuth_deg,sf.usable_fraction,sf.source_kind,sf.source_snapshot_id,sf.confidence_status from solar.surface sf join solar.site st on st.id=sf.site_id where st.project_id=%s order by sf.code",(project_id,)))
    obstacles=rows(conn.execute("select o.id,o.surface_id,o.kind,o.name,o.local_rect,o.height_m,o.clearance_m from solar.obstacle o join solar.surface sf on sf.id=o.surface_id join solar.site st on st.id=sf.site_id where st.project_id=%s",(project_id,)))
    scenarios=rows(conn.execute("select id,name,panel_count,panel_watts,specific_yield_kwh_per_kwp,tariff_brl_per_kwh,capex_cents,status,result,created_at from solar.scenario where project_id=%s order by created_at desc",(project_id,)))
    layouts=rows(conn.execute("select id,site_id,surface_id,scenario_id,name,status,module_code,inverter_code,orientation,panel_count,dc_kwp,local_frame,layout_metrics,engine_version,seed,created_at from solar.layout where project_id=%s order by created_at desc",(project_id,)))
    bills=rows(conn.execute("select reference_month,consumption_kwh,billed_energy_brl,total_bill_brl,tariff_group,distributor,origin,metadata from solar.bill_snapshot where project_id=%s order by reference_month",(project_id,)))
    balances=rows(conn.execute("select id,scenario_id,reference_year,consumption_monthly_kwh,generation_monthly_kwh,self_consumption_monthly_kwh,injected_monthly_kwh,grid_purchase_monthly_kwh,assumptions,created_at from solar.energy_balance where project_id=%s order by created_at desc limit 10",(project_id,)))
    tariffs=rows(conn.execute("select id,distributor,municipality_ibge,reference_date,tariff_brl_per_kwh,source_snapshot_id,assumptions from solar.tariff_snapshot where (tenant_id is null or tenant_id=%s) and reference_date <= %s::date order by reference_date desc limit 20",(tenant_id,base_date)))
    regulations=rows(conn.execute("select id,code,title,authority,valid_from,valid_to,source_snapshot_id,parameters,status,reviewed_by,reviewed_at from solar.regulation_snapshot where (tenant_id is null or tenant_id=%s) and valid_from <= %s::date and (valid_to is null or valid_to > %s::date) order by valid_from desc",(tenant_id,base_date,base_date)))
    latest=scenarios[0] if scenarios else None; latest_balance=balances[0] if balances else None
    has_source=any(x.get('source_snapshot_id') for x in sites+surfaces+tariffs+regulations)
    sections=[
      {'code':'solar_cover','ordinal':1,'title':'Identificação do estudo solar','status':'CONFIRMED','summary':'Estudo preliminar versionado por projeto e data-base.','payload':{'project':project,'baseDate':base_date}},
      {'code':'solar_sources','ordinal':2,'title':'Cobertura e qualidade das fontes','status':'CONFIRMED' if has_source else 'PENDING','summary':'Fontes oficiais/calibradas são distinguidas de entradas do usuário e referências DEMO.','payload':{'sites':sites,'surfaces':surfaces,'tariffs':tariffs,'regulations':regulations}},
      {'code':'solar_site','ordinal':3,'title':'Site e contexto do imóvel','status':'CALCULATED' if sites else 'NOT_AVAILABLE','summary':f'{len(sites)} sites modelados.','payload':{'sites':sites}},
      {'code':'solar_surfaces','ordinal':4,'title':'Superfícies, obstáculos e área útil','status':'CALCULATED' if surfaces else 'NOT_AVAILABLE','summary':f'{len(surfaces)} superfícies e {len(obstacles)} obstáculos.','payload':{'surfaces':surfaces,'obstacles':obstacles}},
      {'code':'solar_sun','ordinal':5,'title':'Trajetória solar e sombreamento','status':'INFERRED' if sites else 'NOT_AVAILABLE','summary':'Posição/trajetória solar preliminar disponível; sombras 3D/DSM ainda não homologadas.','payload':{'method':'NOAA approximation','limitations':['Sem horizonte/DSM/obstáculos 3D calibrados.']}},
      {'code':'solar_equipment','ordinal':6,'title':'Equipamentos selecionados','status':'PENDING' if layouts else 'NOT_AVAILABLE','summary':'Catálogo v18 contém referências DEMO e deve ser substituído/validado por datasheets rastreáveis.','payload':{'layouts':layouts}},
      {'code':'solar_layout','ordinal':7,'title':'Layout 2D e cena 3D preliminar','status':'CALCULATED' if layouts else 'NOT_AVAILABLE','summary':f'{len(layouts)} layouts persistidos.','payload':{'layouts':layouts}},
      {'code':'solar_generation','ordinal':8,'title':'Geração mensal e anual','status':'CALCULATED' if latest and latest.get('result',{}).get('annual_kwh') is not None else 'PENDING','summary':'Geração só é calculada quando yield/irradiância é fornecido por premissa rastreável.','payload':{'scenarios':scenarios[:10]}},
      {'code':'solar_consumption','ordinal':9,'title':'Consumo, autoconsumo e injeção','status':'CALCULATED' if latest_balance else ('PENDING' if bills else 'NOT_AVAILABLE'),'summary':f'{len(bills)} contas/snapshots e {len(balances)} balanços mensais.','payload':{'bills':bills,'balances':balances}},
      {'code':'solar_tariff','ordinal':10,'title':'Distribuidora, tarifa e regulação','status':'CONFIRMED' if any(x.get('source_snapshot_id') for x in tariffs+regulations) else ('PENDING' if tariffs or regulations else 'NOT_AVAILABLE'),'summary':'Tarifa e regulação precisam de fonte/versão; não são inferidas pelo motor.','payload':{'tariffs':tariffs,'regulations':regulations}},
      {'code':'solar_finance','ordinal':11,'title':'CAPEX/OPEX e financeiro','status':'CALCULATED' if latest and latest.get('result',{}).get('npv_brl') is not None else 'PENDING','summary':'Payback, VPL e LCOE usam premissas explícitas.','payload':{'scenarios':scenarios[:10]}},
      {'code':'solar_connection','ordinal':12,'title':'Rede e conexão','status':'NOT_AVAILABLE','summary':'Pré-check de BDGD/pedido de conexão ainda requer integração oficial.','payload':{}},
      {'code':'solar_constraints','ordinal':13,'title':'Estrutura, incêndio, patrimônio, condomínio e zoneamento','status':'PENDING','summary':'Condicionantes externas devem vir dos módulos territoriais/Condomínio e de revisão profissional.','payload':{}},
      {'code':'solar_evidence','ordinal':14,'title':'Evidências, versões e premissas','status':'PENDING' if not has_source else 'CONFIRMED','summary':'O relatório diferencia fonte oficial, premissa do usuário e referência DEMO.','payload':{'sites':sites,'surfaces':surfaces,'tariffs':tariffs,'regulations':regulations}},
      {'code':'solar_limitations','ordinal':15,'title':'Limitações e próximos passos','status':'PENDING','summary':'Estudo preliminar, não projeto executivo.','payload':{'limitations':['Não há validação estrutural da cobertura nesta release.','Sombreamento 3D/DSM, strings/inversores, clipping e estudo de acesso/conexão ainda exigem aprofundamento.','Equipamentos REFERENCE/DEMO não constituem recomendação comercial.','Nenhum resultado substitui projeto e responsabilidade técnica quando exigidos.']}}
    ]
    counts=Counter(x['status'] for x in sections)
    return primitive({'schemaVersion':'solar-360-v1','template':template,'report':{'id':report_run['id'],'kind':report_run['kind'],'base_date':base_date},'analysis':{'base_date':base_date,'status':'SOLAR_PRELIMINARY_STUDY'},'project':project,'confidenceSummary':{'confirmed':counts['CONFIRMED'],'calculated':counts['CALCULATED'],'inferred':counts['INFERRED'],'pending':counts['PENDING'],'conflicting':counts['CONFLICTING'],'not_available':counts['NOT_AVAILABLE']},'sections':sections,'evidence':[],'disclaimers':['Energia Solar 360 v18 é estudo preliminar e não substitui projeto executivo, vistoria ou parecer da distribuidora.','Resultados financeiros dependem das premissas e da regulação/tarifa vigentes na data-base.']})

def build_report(conn, tenant_id: str, report_run: dict[str, Any]) -> dict[str, Any]:
    template_code = report_run.get('template_code') or 'PROPERTY360_360'
    template = one(conn.execute("select code,version,title,subject_types,section_order from report.template where code=%s and status='ACTIVE'", (template_code,)))
    if not template:
        raise ValueError('report_template_not_found')
    if report_run['subject_type'] == 'analysis':
        return build_analysis_report(conn, tenant_id, report_run, template)
    if report_run['subject_type'] == 'rural_asset':
        return build_rural_report(conn, tenant_id, report_run, template)
    if report_run['subject_type'] == 'condominium':
        return build_condo_report(conn, tenant_id, report_run, template)
    if report_run['subject_type'] == 'solar_project':
        return build_solar_report(conn, tenant_id, report_run, template)
    raise ValueError(f"unsupported_report_subject:{report_run['subject_type']}")


def canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
