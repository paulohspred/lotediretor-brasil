from __future__ import annotations
import io, json, math
from typing import Any
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Flowable

STATUS_COLORS = {
    'CONFIRMED': colors.HexColor('#2E7D32'),
    'CALCULATED': colors.HexColor('#1565C0'),
    'INFERRED': colors.HexColor('#EF6C00'),
    'PENDING': colors.HexColor('#F9A825'),
    'CONFLICTING': colors.HexColor('#C62828'),
    'NOT_AVAILABLE': colors.HexColor('#616161'),
}

class ParcelSketch(Flowable):
    def __init__(self, geometry: dict[str, Any] | None, width=160*mm, height=65*mm):
        super().__init__(); self.geometry=geometry; self.width=width; self.height=height
    def wrap(self, availWidth, availHeight): return min(self.width, availWidth), self.height
    def draw(self):
        c=self.canv; w,h=self.width,self.height
        c.setStrokeColor(colors.HexColor('#9CA3AF')); c.rect(0,0,w,h,stroke=1,fill=0)
        if not self.geometry:
            c.setFillColor(colors.HexColor('#6B7280')); c.setFont('Helvetica',8); c.drawCentredString(w/2,h/2,'Geometria não disponível para o snapshot do relatório.'); return
        coords=[]
        typ=self.geometry.get('type'); raw=self.geometry.get('coordinates') or []
        if typ=='Polygon' and raw: coords=raw[0]
        elif typ=='MultiPolygon' and raw and raw[0]: coords=raw[0][0]
        if len(coords)<3:
            c.setFont('Helvetica',8); c.drawCentredString(w/2,h/2,'Geometria não renderizável.'); return
        xs=[float(p[0]) for p in coords]; ys=[float(p[1]) for p in coords]
        minx,maxx,miny,maxy=min(xs),max(xs),min(ys),max(ys); dx=max(maxx-minx,1e-9);dy=max(maxy-miny,1e-9)
        margin=8*mm; scale=min((w-2*margin)/dx,(h-2*margin)/dy)
        pts=[(margin+(x-minx)*scale,margin+(y-miny)*scale) for x,y in zip(xs,ys)]
        path=c.beginPath(); path.moveTo(*pts[0])
        for p in pts[1:]: path.lineTo(*p)
        path.close(); c.setFillColor(colors.HexColor('#E8F5E9')); c.setStrokeColor(colors.HexColor('#20A475')); c.setLineWidth(1.4); c.drawPath(path,stroke=1,fill=1)
        c.setFillColor(colors.HexColor('#374151')); c.setFont('Helvetica',7); c.drawString(4*mm,3*mm,'Croqui vetorial do polígono analisado; não substitui planta/certidão cadastral.')


def _safe(value: Any) -> str:
    if value is None: return '—'
    if isinstance(value, (dict,list)): return json.dumps(value,ensure_ascii=False,sort_keys=True)
    return str(value)


def _status_badge(status: str, styles):
    color=STATUS_COLORS.get(status,colors.HexColor('#616161'))
    return Table([[Paragraph(f'<b>{status}</b>', styles['ld_badge'])]],style=TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),color),('TEXTCOLOR',(0,0),(-1,-1),colors.white),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)
    ]))


def _kv_table(mapping: dict[str, Any], styles, keys: list[tuple[str,str]]):
    data=[]
    for key,label in keys:
        if key in mapping and mapping.get(key) is not None:
            data.append([Paragraph(f'<b>{label}</b>',styles['ld_small']),Paragraph(_safe(mapping.get(key)),styles['ld_small'])])
    if not data: return Paragraph('Sem dados estruturados nesta seção.',styles['ld_muted'])
    t=Table(data,colWidths=[48*mm,112*mm],repeatRows=0)
    t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),0.25,colors.HexColor('#E5E7EB')),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#F9FAFB')),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    return t


def _list_table(items: list[dict[str, Any]], styles, columns: list[tuple[str,str]], limit=30):
    if not items: return Paragraph('Nenhum item disponível.',styles['ld_muted'])
    header=[Paragraph(f'<b>{label}</b>',styles['ld_tiny']) for _,label in columns]
    data=[header]
    for item in items[:limit]: data.append([Paragraph(_safe(item.get(key)),styles['ld_tiny']) for key,_ in columns])
    widths=[160*mm/len(columns)]*len(columns)
    t=Table(data,colWidths=widths,repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#F3F4F6')),('GRID',(0,0),(-1,-1),0.25,colors.HexColor('#D1D5DB')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
    return t


def _section_story(section: dict[str, Any], styles):
    out=[]; status=section.get('status','NOT_AVAILABLE'); payload=section.get('payload') or {}; code=section.get('code')
    out.append(KeepTogether([Table([[Paragraph(f"<b>{section.get('ordinal')}. {section.get('title')}</b>",styles['ld_h2']),_status_badge(status,styles)]],colWidths=[135*mm,25*mm],style=TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('BOTTOMPADDING',(0,0),(-1,-1),5)])),Paragraph(section.get('summary') or '',styles['ld_body'])]))
    out.append(Spacer(1,3*mm))
    if code in ('cover','identification'):
        parcel=payload.get('parcel') or {}; prop=payload.get('property') or {}
        out.append(_kv_table({**parcel,**{'propertyName':prop.get('name'),'address':prop.get('address'),'propertyStatus':prop.get('status')}},styles,[('propertyName','Imóvel'),('address','Endereço'),('propertyStatus','Status do imóvel'),('municipality_ibge','Município IBGE'),('official_identifier','Identificador oficial'),('area_m2','Área geodésica (m²)'),('perimeter_m','Perímetro (m)'),('centroid_lat','Latitude centroide'),('centroid_lon','Longitude centroide')]))
    elif code=='map':
        out.append(ParcelSketch(payload.get('geometry')))
    elif code in ('urban','parameters','uses','instruments'):
        items=payload.get('parameters') or payload.get('rules') or []
        out.append(_list_table(items,styles,[('parameter','Parâmetro'),('value_numeric','Valor'),('value_text','Texto'),('unit','Unidade'),('status','Status'),('source_locator','Fonte/localizador')],limit=40))
        conflicts=payload.get('conflicts') or []
        if conflicts:
            out.append(Spacer(1,2*mm));out.append(Paragraph('<b>Conflitos normativos abertos</b>',styles['ld_body']));out.append(_list_table(conflicts,styles,[('parameter','Parâmetro'),('reason','Motivo'),('status','Status')],limit=20))
    elif code=='potential':
        out.append(_list_table(payload.get('calculations') or [],styles,[('code','Cálculo'),('value_numeric','Valor'),('unit','Unidade'),('formula','Fórmula'),('status','Status')],limit=30))
    elif code in ('environment','risk','infrastructure','mobility','heritage','licensing'):
        out.append(_list_table(payload.get('relations') or [],styles,[('layer_code','Camada'),('layer_title','Descrição'),('intersection_area_m2','Interseção m²'),('intersection_ratio','Razão'),('distance_m','Distância m')],limit=40))
    elif code=='fiscal_market':
        out.append(_list_table(payload.get('avmRuns') or [],styles,[('model_version','Modelo'),('estimate_cents','Estimativa centavos'),('confidence','Confiança'),('status','Status'),('created_at','Data')],limit=20))
    elif code=='diligence':
        out.append(_list_table(payload.get('diligences') or [],styles,[('title','Diligência'),('status','Status'),('priority','Prioridade'),('due_at','Prazo')],limit=30))
        notes=payload.get('notes') or []
        if notes:
            out.append(Spacer(1,2*mm));out.append(Paragraph('<b>Notas do imóvel</b>',styles['ld_body']));out.append(_list_table(notes,styles,[('body','Nota'),('tags','Tags'),('created_at','Data')],limit=30))
    elif code=='evidence':
        out.append(_list_table(payload.get('snapshots') or [],styles,[('source_code','Fonte'),('authority','Órgão'),('source_date','Data fonte'),('parser_version','Parser'),('sha256','SHA-256')],limit=40))
    elif code=='rural_cover':
        asset=payload.get('asset') or {};out.append(_kv_table(asset,styles,[('name','Ativo'),('municipality_ibge','Município IBGE'),('area_m2','Área m²')]))
        out.append(ParcelSketch(asset.get('geometry')))
    elif code=='rural_identity':
        out.append(_list_table(payload.get('links') or [],styles,[('relationship','Relação'),('confidence','Confiança'),('status','Status'),('reasons','Razões')],limit=40))
        out.append(_list_table(payload.get('identifiers') or [],styles,[('identifier_type','Identificador'),('identifier_value','Valor'),('status','Status')],limit=40))
    elif code=='rural_registries':
        out.append(_list_table(payload.get('records') or [],styles,[('registry_type','Registro'),('official_identifier','Identificador'),('authority','Órgão'),('source_date','Data fonte'),('validation_status','QA'),('area_m2','Área m²')],limit=60))
    elif code=='rural_convergence':
        out.append(_list_table(payload.get('overlaps') or [],styles,[('overlap_type','Fonte'),('overlap_area_m2','Interseção m²'),('overlap_ratio','% ativo'),('calculated_at','Calculado em')],limit=60))
    elif code=='rural_environment':
        out.append(_list_table(payload.get('layerHits') or [],styles,[('code','Camada'),('authority','Órgão'),('official_identifier','Identificador'),('intersection_area_m2','Interseção m²'),('intersection_ratio','Razão')],limit=60))
    elif code=='rural_monitoring':
        out.append(_list_table(payload.get('monitors') or [],styles,[('monitor_type','Monitor'),('status','Status'),('last_checked_at','Última checagem'),('last_change_at','Última mudança'),('event_count','Eventos')],limit=40))
        out.append(_list_table(payload.get('events') or [],styles,[('event_type','Evento'),('status','Status'),('detected_at','Detectado em'),('change_summary','Mudança')],limit=40))
    elif code=='rural_credit':
        out.append(_list_table(payload.get('records') or [],styles,[('registry_type','Camada'),('official_identifier','Identificador'),('source_date','Data fonte'),('validation_status','QA')],limit=30))
    elif code=='rural_evidence':
        out.append(_list_table(payload.get('evidence') or [],styles,[('evidenceType','Tipo'),('sourceCode','Fonte'),('sha256','SHA-256'),('confidenceStatus','Status')],limit=60))
        out.append(_list_table(payload.get('exports') or [],styles,[('format','Formato'),('status','Status'),('sha256','SHA-256'),('completed_at','Concluído')],limit=30))
    elif code=='rural_limitations':
        for limitation in payload.get('limitations') or []: out.append(Paragraph(f'• {limitation}',styles['ld_muted']))
    elif code=='condo_cover':
        out.append(_kv_table(payload.get('condominium') or {},styles,[('name','Condomínio'),('kind','Tipo'),('municipality_ibge','Município IBGE'),('created_at','Criado em')]))
    elif code=='condo_documents':
        out.append(_list_table(payload.get('documents') or [],styles,[('kind','Tipo'),('title','Documento'),('processing_status','Processamento'),('sha256','SHA-256')],limit=50))
    elif code=='condo_rules':
        out.append(_list_table(payload.get('rules') or [],styles,[('rule_type','Tipo'),('title','Regra'),('status','Status'),('source_locator','Localizador'),('valid_from','Vigência inicial'),('valid_to','Vigência final')],limit=70))
    elif code=='condo_units':
        out.append(_list_table(payload.get('buildings') or [],styles,[('code','Bloco'),('name','Nome'),('floors','Pavimentos')],limit=30))
        out.append(_list_table(payload.get('units') or [],styles,[('building_code','Bloco'),('code','Unidade'),('kind','Tipo'),('private_area_m2','Área privativa'),('fraction','Fração'),('status','Status')],limit=80))
        out.append(_list_table(payload.get('commonAreas') or [],styles,[('code','Área'),('name','Nome'),('kind','Tipo'),('area_m2','Área m²')],limit=40))
    elif code=='condo_works':
        out.append(_list_table(payload.get('works') or [],styles,[('title','Obra/reforma'),('work_type','Tipo'),('status','Status'),('art_rrt_reference','ART/RRT'),('technical_responsible','Responsável'),('decision_reason','Decisão')],limit=60))
    elif code=='condo_assemblies':
        out.append(_list_table(payload.get('assemblies') or [],styles,[('title','Assembleia'),('scheduled_at','Data'),('status','Status'),('kind','Tipo')],limit=40))
        out.append(_list_table(payload.get('decisions') or [],styles,[('title','Deliberação'),('status','Status'),('decision_text','Decisão'),('source_locator','Fonte')],limit=50))
        out.append(_list_table(payload.get('voteSummaries') or [],styles,[('present_count','Presentes'),('favorable_count','Favoráveis'),('contrary_count','Contrários'),('abstention_count','Abstenções'),('fraction_favorable','Fração favorável'),('quorum_result','Quórum')],limit=50))
    elif code=='condo_maintenance':
        out.append(_list_table(payload.get('maintenance') or [],styles,[('system_code','Sistema'),('title','Item'),('status','Status'),('last_done_at','Última execução'),('next_due_at','Próximo vencimento')],limit=60))
    elif code=='condo_occurrences':
        out.append(_list_table(payload.get('occurrences') or [],styles,[('category','Categoria'),('title','Ocorrência'),('severity','Severidade'),('status','Status'),('defense_due_at','Defesa até'),('resolution','Resolução')],limit=60))
    elif code=='condo_compliance':
        out.append(_list_table(payload.get('compliance') or [],styles,[('code','Código'),('title','Obrigação'),('category','Categoria'),('status','Status'),('due_at','Prazo'),('responsible','Responsável')],limit=60))
    elif code=='condo_evidence':
        out.append(_list_table(payload.get('evidence') or [],styles,[('document_title','Documento'),('locator','Localizador'),('document_sha256','SHA-256')],limit=80))
    elif code=='condo_limitations':
        for limitation in payload.get('limitations') or []: out.append(Paragraph(f'• {limitation}',styles['ld_muted']))
    elif code=='solar_cover':
        out.append(_kv_table(payload.get('project') or {},styles,[('name','Projeto'),('status','Status'),('property_id','Imóvel vinculado'),('created_at','Criado em')]))
    elif code in ('solar_sources','solar_evidence'):
        out.append(_list_table(payload.get('sites') or [],styles,[('name','Site'),('kind','Tipo'),('municipality_ibge','Município'),('source_snapshot_id','Snapshot')],limit=30))
        out.append(_list_table(payload.get('tariffs') or [],styles,[('distributor','Distribuidora'),('reference_date','Data'),('tariff_brl_per_kwh','Tarifa R$/kWh'),('source_snapshot_id','Snapshot')],limit=30))
        out.append(_list_table(payload.get('regulations') or [],styles,[('code','Regra'),('title','Título'),('authority','Órgão'),('valid_from','Vigência'),('status','Status')],limit=30))
    elif code=='solar_site':
        out.append(_list_table(payload.get('sites') or [],styles,[('name','Site'),('kind','Tipo'),('municipality_ibge','Município'),('latitude','Latitude'),('longitude','Longitude'),('elevation_m','Elevação')],limit=30))
    elif code=='solar_surfaces':
        out.append(_list_table(payload.get('surfaces') or [],styles,[('code','Superfície'),('kind','Tipo'),('area_m2','Área m²'),('pitch_deg','Inclinação'),('azimuth_deg','Azimute'),('usable_fraction','Fração útil'),('confidence_status','Confiança')],limit=50))
        out.append(_list_table(payload.get('obstacles') or [],styles,[('kind','Obstáculo'),('name','Nome'),('height_m','Altura'),('clearance_m','Afastamento')],limit=50))
    elif code=='solar_sun':
        out.append(Paragraph(_safe(payload.get('method') or 'Método não informado'),styles['ld_body']))
        for limitation in payload.get('limitations') or []: out.append(Paragraph(f'• {limitation}',styles['ld_muted']))
    elif code in ('solar_equipment','solar_layout'):
        out.append(_list_table(payload.get('layouts') or [],styles,[('name','Layout'),('status','Status'),('module_code','Módulo'),('inverter_code','Inversor'),('orientation','Orientação'),('panel_count','Painéis'),('dc_kwp','kWp'),('engine_version','Motor')],limit=40))
    elif code in ('solar_generation','solar_finance'):
        out.append(_list_table(payload.get('scenarios') or [],styles,[('name','Cenário'),('status','Status'),('panel_count','Painéis'),('panel_watts','W/painel'),('specific_yield_kwh_per_kwp','Yield'),('tariff_brl_per_kwh','Tarifa'),('capex_cents','CAPEX centavos')],limit=30))
    elif code=='solar_consumption':
        out.append(_list_table(payload.get('bills') or [],styles,[('reference_month','Mês'),('consumption_kwh','Consumo kWh'),('total_bill_brl','Conta R$'),('distributor','Distribuidora'),('origin','Origem')],limit=24))
        out.append(_list_table(payload.get('balances') or [],styles,[('reference_year','Ano'),('scenario_id','Cenário'),('assumptions','Premissas')],limit=10))
    elif code=='solar_tariff':
        out.append(_list_table(payload.get('tariffs') or [],styles,[('distributor','Distribuidora'),('reference_date','Data'),('tariff_brl_per_kwh','Tarifa'),('source_snapshot_id','Snapshot')],limit=30))
        out.append(_list_table(payload.get('regulations') or [],styles,[('code','Regra'),('title','Título'),('authority','Órgão'),('valid_from','Vigência'),('status','Status')],limit=30))
    elif code in ('solar_connection','solar_constraints'):
        if payload: out.append(Paragraph(_safe(payload),styles['ld_tiny']))
    elif code=='solar_limitations':
        for limitation in payload.get('limitations') or []: out.append(Paragraph(f'• {limitation}',styles['ld_muted']))
    elif code=='executive':
        out.append(_list_table(payload.get('critical') or [],styles,[('kind','Tipo'),('code','Código'),('title','Achado'),('value','Valor'),('unit','Unidade'),('status','Status')],limit=20))
        for limitation in payload.get('limitations') or []: out.append(Paragraph(f'• {limitation}',styles['ld_muted']))
    else:
        if payload: out.append(Paragraph(_safe(payload),styles['ld_tiny']))
    out.append(Spacer(1,5*mm));return out


def render_structured(document: dict[str, Any]) -> bytes:
    buf=io.BytesIO(); styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='title2',parent=styles['Title'],fontName='Helvetica-Bold',fontSize=18,leading=22,textColor=colors.HexColor('#111827'),spaceAfter=8))
    styles.add(ParagraphStyle(name='ld_h2',parent=styles['Heading2'],fontName='Helvetica-Bold',fontSize=11,leading=14,textColor=colors.HexColor('#1F4035')))
    styles.add(ParagraphStyle(name='ld_body',parent=styles['BodyText'],fontName='Helvetica',fontSize=8.8,leading=12,textColor=colors.HexColor('#111827')))
    styles.add(ParagraphStyle(name='ld_small',parent=styles['BodyText'],fontName='Helvetica',fontSize=7.8,leading=10))
    styles.add(ParagraphStyle(name='ld_tiny',parent=styles['BodyText'],fontName='Helvetica',fontSize=6.7,leading=8.5))
    styles.add(ParagraphStyle(name='ld_muted',parent=styles['BodyText'],fontName='Helvetica-Oblique',fontSize=7.8,leading=10,textColor=colors.HexColor('#6B7280')))
    styles.add(ParagraphStyle(name='ld_badge',parent=styles['BodyText'],fontName='Helvetica-Bold',fontSize=6.5,leading=7,alignment=TA_LEFT))
    report=document.get('report') or {}; template=document.get('template') or {}; analysis=document.get('analysis') or {}; confidence=document.get('confidenceSummary') or {}
    def footer(canvas,doc):
        canvas.saveState(); canvas.setFont('Helvetica',7);canvas.setFillColor(colors.HexColor('#6B7280'));canvas.drawString(18*mm,10*mm,f"LoteDiretor Brasil · {template.get('code','REPORT')} v{template.get('version','1')}");canvas.drawRightString(192*mm,10*mm,f"p. {doc.page}");canvas.restoreState()
    doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=18*mm,bottomMargin=16*mm,title=template.get('title','LoteDiretor Brasil — Relatório técnico'),author='LoteDiretor Brasil')
    story=[Paragraph(template.get('title','LoteDiretor Brasil — Relatório técnico'),styles['title2']),Paragraph(f"Relatório {report.get('id','')} · data-base {analysis.get('base_date') or report.get('base_date') or 'não informada'}",styles['ld_body']),Spacer(1,3*mm)]
    story.append(_kv_table({'schemaVersion':document.get('schemaVersion'),'analysisStatus':analysis.get('status'),'confirmed':confidence.get('confirmed',0),'calculated':confidence.get('calculated',0),'pending':confidence.get('pending',0),'conflicting':confidence.get('conflicting',0),'notAvailable':confidence.get('not_available',0)},styles,[('schemaVersion','Schema'),('analysisStatus','Status da análise'),('confirmed','Seções confirmadas'),('calculated','Seções calculadas'),('pending','Seções pendentes'),('conflicting','Seções conflitantes'),('notAvailable','Seções não disponíveis')]))
    story.append(Spacer(1,5*mm))
    for section in document.get('sections') or []: story.extend(_section_story(section,styles))
    story.append(PageBreak());story.append(Paragraph('Disclaimers e limitações',styles['ld_h2']))
    for item in document.get('disclaimers') or []: story.append(Paragraph(f'• {item}',styles['ld_body']))
    doc.build(story,onFirstPage=footer,onLaterPages=footer);return buf.getvalue()

# Legacy compatibility for tests and older calls.
def render(title:str,lines:list[str])->bytes:
    document={'schemaVersion':'legacy-v1','template':{'code':'LEGACY','version':1,'title':title},'report':{},'analysis':{},'confidenceSummary':{},'sections':[{'code':'executive','ordinal':1,'title':'Conteúdo','status':'CALCULATED','summary':'Relatório legado.','payload':{'critical':[{'kind':'LINE','title':str(x),'status':'CALCULATED'} for x in lines]}}],'disclaimers':[]}
    return render_structured(document)
