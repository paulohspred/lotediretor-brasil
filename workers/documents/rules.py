from __future__ import annotations
import re

def condo_candidates(text:str):
    """Conservative condominium rule extraction.

    Only explicit normative language becomes CANDIDATE. Human review is still
    required before a rule can become CONFIRMED.
    """
    patterns=[
      ('PROHIBITION', re.compile(r'(?i)\b(?:é|fica|ficam|é\s+expressamente)\s+proibid[oa]s?\b|\bnão\s+é\s+permitid[oa]s?\b')),
      ('PERMISSION', re.compile(r'(?i)\b(?:é|fica|ficam)\s+permitid[oa]s?\b|\bpoderá\b|\bpoderão\b')),
      ('CONDITION', re.compile(r'(?i)\b(?:somente|apenas)\s+(?:será|serão|poderá|poderão)|\bmediante\s+(?:autorização|aprovação)|\bdepende\s+de\s+(?:autorização|aprovação)|\bnecessita\s+de\s+(?:autorização|aprovação)')),
      ('QUORUM', re.compile(r'(?i)\b(?:quórum|quorum)\b|\b(?:dois\s+terços|2\s*/\s*3|maioria\s+absoluta|maioria\s+simples)\b')),
      ('OBLIGATION', re.compile(r'(?i)\b(?:deverá|deverão|é\s+obrigatóri[oa]|são\s+obrigatóri[oa]s)\b')),
    ]
    lines=[x.strip() for x in text.splitlines() if x.strip()]
    out=[]
    for idx,line in enumerate(lines,1):
      if len(line)<18 or len(line)>1600: continue
      kinds=[kind for kind,rx in patterns if rx.search(line)]
      if not kinds or len(line.split())<5: continue
      out.append({'rule_type':kinds[0],'title':line[:120],'rule_text':line,'source_locator':f'line:{idx}','confidence':0.62 if kinds[0] != 'QUORUM' else 0.55})
      if len(out)>=120:break
    return out

_PAGE_MARKER=re.compile(r'^<<<PAGE:(\d+)>>>$')
_HEADING_PATTERNS=[
  ('BOOK',re.compile(r'(?i)^\s*LIVRO\s+([IVXLCDM]+|\w+)\b(?:\s*[-–—:]\s*(.*))?$')),
  ('TITLE',re.compile(r'(?i)^\s*T[IÍ]TULO\s+([IVXLCDM]+|\w+)\b(?:\s*[-–—:]\s*(.*))?$')),
  ('CHAPTER',re.compile(r'(?i)^\s*CAP[IÍ]TULO\s+([IVXLCDM]+|\w+)\b(?:\s*[-–—:]\s*(.*))?$')),
  ('SECTION',re.compile(r'(?i)^\s*SE[CÇ][AÃ]O\s+([IVXLCDM]+|\w+)\b(?:\s*[-–—:]\s*(.*))?$')),
  ('SUBSECTION',re.compile(r'(?i)^\s*SUBSE[CÇ][AÃ]O\s+([IVXLCDM]+|\w+)\b(?:\s*[-–—:]\s*(.*))?$')),
]
_ARTICLE_RE=re.compile(r'(?i)^\s*Art(?:igo)?\.?\s*(\d+[A-Za-z]?(?:[-º°]\w+)?)\s*[º°o]?\s*[.\-–—:]?\s*(.*)$')


def legal_units(text:str):
    """Line-aware legal structure extraction with page/article locators.

    It intentionally does not decide legal meaning or validity. It only creates a
    reproducible document hierarchy that later rule candidates can point back to.
    """
    page=None; hierarchy=[]; units=[]; current=None; ordinal=0
    def flush():
        nonlocal current
        if not current:return
        body='\n'.join(current.pop('_body')).strip()
        current['body_text']=body or current.get('heading') or current.get('label') or ''
        units.append(current);current=None
    for raw in text.splitlines():
        line=raw.strip()
        if not line:continue
        pm=_PAGE_MARKER.match(line)
        if pm:page=int(pm.group(1));continue
        heading=None
        for level,rx in _HEADING_PATTERNS:
            m=rx.match(line)
            if m:heading=(level,m.group(1),m.group(2) or '');break
        if heading:
            flush();level,label,title=heading
            levels=['BOOK','TITLE','CHAPTER','SECTION','SUBSECTION'];rank=levels.index(level)
            hierarchy[:]=[h for h in hierarchy if levels.index(h[0])<rank]
            hierarchy.append((level,label))
            ordinal+=1;path='/'.join(f'{a}:{b}' for a,b in hierarchy)
            current={'article_type':level,'label':label,'heading':title or line,'hierarchy_path':path,'ordinal':ordinal,'source_locator':f'page:{page or "?"}#{path}','page':page,'_body':[line]}
            continue
        am=_ARTICLE_RE.match(line)
        if am:
            flush();label=am.group(1);tail=am.group(2) or '';ordinal+=1
            prefix='/'.join(f'{a}:{b}' for a,b in hierarchy);path=f'{prefix}/ARTICLE:{label}' if prefix else f'ARTICLE:{label}'
            current={'article_type':'ARTICLE','label':label,'heading':None,'hierarchy_path':path,'ordinal':ordinal,'source_locator':f'page:{page or "?"}#art:{label}','page':page,'_body':[tail] if tail else []}
            continue
        if current is None:
            # Preamble is useful evidence but not a legal article.
            if units and units[-1]['article_type']=='PREAMBLE':units[-1]['body_text']+='\n'+line
            else:
                ordinal+=1;units.append({'article_type':'PREAMBLE','label':None,'heading':None,'hierarchy_path':'PREAMBLE','ordinal':ordinal,'source_locator':f'page:{page or "?"}#preamble','page':page,'body_text':line})
        else:current['_body'].append(line)
    flush()
    # Avoid duplicate hierarchy paths when malformed PDFs repeat headings; preserve a stable suffix.
    seen={};out=[]
    for u in units:
        base=u['hierarchy_path'];n=seen.get(base,0)+1;seen[base]=n
        if n>1:u['hierarchy_path']=f'{base}~{n}'
        out.append(u)
    return out

def _condition_from_context(text:str):
    """Extract only explicit applicability conditions from a short legal context.

    The output matches the platform rule-condition contract. Ambiguous prose is
    ignored rather than guessed.
    """
    clauses=[]
    normalized=' '.join(text.split())
    patterns=[
      ('lot_area_m2','lte',r'(?i)\b(?:lotes?|área\s+do\s+lote)\b.{0,55}?\b(?:até|igual\s+ou\s+inferior\s+a|menor\s+ou\s+igual\s+a|no\s+máximo)\s*(\d+(?:[.,]\d+)?)\s*m[²2]\b'),
      ('lot_area_m2','gt',r'(?i)\b(?:lotes?|área\s+do\s+lote)\b.{0,55}?\b(?:acima\s+de|superior\s+a|maior\s+que)\s*(\d+(?:[.,]\d+)?)\s*m[²2]\b'),
      ('lot_area_m2','gte',r'(?i)\b(?:lotes?|área\s+do\s+lote)\b.{0,55}?\b(?:a\s+partir\s+de|igual\s+ou\s+superior\s+a|maior\s+ou\s+igual\s+a|mínimo\s+de)\s*(\d+(?:[.,]\d+)?)\s*m[²2]\b'),
      ('frontage_m','gte',r'(?i)\b(?:testada|frente)\b.{0,45}?\b(?:a\s+partir\s+de|igual\s+ou\s+superior\s+a|maior\s+ou\s+igual\s+a|mínim[oa]\s+de)\s*(\d+(?:[.,]\d+)?)\s*(?:m|metros?)\b'),
      ('road_width_m','gte',r'(?i)\b(?:largura\s+da\s+via|via)\b.{0,45}?\b(?:a\s+partir\s+de|igual\s+ou\s+superior\s+a|maior\s+ou\s+igual\s+a|mínim[oa]\s+de)\s*(\d+(?:[.,]\d+)?)\s*(?:m|metros?)\b'),
    ]
    for field,op,rx in patterns:
      m=re.search(rx,normalized)
      if m:
        try:value=float(m.group(1).replace(',','.'))
        except Exception:continue
        clauses.append({'field':field,'op':op,'value':value})
    # A categorical condition is accepted only when the text explicitly scopes the rule.
    if re.search(r'(?i)\b(?:para|nos?|em)\s+lotes?\s+de\s+esquina\b',normalized):
      clauses.append({'field':'corner_lot','op':'eq','value':True})
    # Prefer a bounded interval when the same sentence states one explicitly.
    m=re.search(r'(?i)\b(?:lotes?|área\s+do\s+lote)\b.{0,45}?\bentre\s*(\d+(?:[.,]\d+)?)\s*(?:m[²2])?\s*e\s*(\d+(?:[.,]\d+)?)\s*m[²2]\b',normalized)
    if m:
      try:
        lo=float(m.group(1).replace(',','.'));hi=float(m.group(2).replace(',','.'))
        clauses=[x for x in clauses if x.get('field')!='lot_area_m2']
        clauses.append({'field':'lot_area_m2','op':'between','min':min(lo,hi),'max':max(lo,hi)})
      except Exception:pass
    if not clauses:return {}
    return clauses[0] if len(clauses)==1 else {'all':clauses}


def legal_candidates(text:str, locator_prefix:str|None=None):
    """Extract conservative computable urban parameters as CANDIDATE only.

    Executable applicability is kept in ``condition``. Extraction provenance is
    returned separately so database code does not accidentally execute parser
    metadata as a legal condition.
    """
    specs=[
      ('CA_MIN', r'(?i)\b(?:coeficiente\s+de\s+aproveitamento|c\.?a\.?)\s*(?:m[ií]nimo|min\.?|m[ií]n\.?)\s*[:=]?\s*(\d+(?:[.,]\d+)?)', None),
      ('CA_BASIC', r'(?i)\b(?:coeficiente\s+de\s+aproveitamento|c\.?a\.?)\s*(?:b[aá]sico|b[aá]s\.?)\s*[:=]?\s*(\d+(?:[.,]\d+)?)', None),
      ('CA_MAX', r'(?i)\b(?:coeficiente\s+de\s+aproveitamento|c\.?a\.?)\s*(?:m[aá]ximo|max\.?|m[aá]x\.?)\s*[:=]?\s*(\d+(?:[.,]\d+)?)', None),
      ('TO_MAX', r'(?i)\b(?:taxa\s+de\s+ocupa[cç][aã]o|t\.?o\.?)\s*(?:m[aá]xima|max\.?|m[aá]x\.?)?\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(%|por\s+cento\b)', '%'),
      ('TP_MIN', r'(?i)\b(?:taxa\s+de\s+permeabilidade|t\.?p\.?)\s*(?:m[ií]nima|min\.?|m[ií]n\.?)?\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(%|por\s+cento\b)', '%'),
      ('HEIGHT_MAX_M', r'(?i)\b(?:gabarito|altura\s+m[aá]xima)\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:m|metros?)\b', 'm'),
      ('FLOORS_MAX', r'(?i)\b(?:n[uú]mero\s+m[aá]ximo\s+de\s+pavimentos|m[aá]ximo\s+de\s+pavimentos|at[eé]\s+)\s*[:=]?\s*(\d+)\s*pavimentos?\b', 'pavimentos'),
      ('SETBACK_FRONT_M', r'(?i)\b(?:recuo|afastamento)\s+frontal\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:m|metros?)\b', 'm'),
      ('SETBACK_SIDE_M', r'(?i)\b(?:recuo|afastamento)\s+lateral\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:m|metros?)\b', 'm'),
      ('SETBACK_REAR_M', r'(?i)\b(?:recuo|afastamento)\s+(?:de\s+)?fundos\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:m|metros?)\b', 'm'),
      ('LOT_MIN_AREA_M2', r'(?i)\b(?:lote|área)\s+m[ií]nim[oa]\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*m[²2]\b', 'm²'),
      ('FRONTAGE_MIN_M', r'(?i)\b(?:testada|frente)\s+m[ií]nima\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:m|metros?)\b', 'm'),
      ('DENSITY_MAX_U_HA', r'(?i)\b(?:densidade\s+m[aá]xima|unidades\s+por\s+hectare)\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:unidades?\s*/?\s*ha|u\s*/\s*ha)\b', 'un/ha'),
    ]
    out=[]
    for parameter,pattern,unit in specs:
      for m in re.finditer(pattern,text):
        try:value=float(m.group(1).replace(',','.'))
        except Exception:continue
        # Conditions must be close enough to the numeric rule to avoid borrowing a
        # qualifier from an unrelated paragraph.
        start=max(0,m.start()-180);end=min(len(text),m.end()+260);context=text[start:end]
        out.append({
          'parameter':parameter,'value':value,'unit':unit,
          'condition':_condition_from_context(context),
          'excerpt':context.replace('\n',' '),'offset':m.start(),'source_locator':locator_prefix,
          'extractor':'deterministic_legal_v19_beta'
        })
        if len(out)>=160:return out
    return out
