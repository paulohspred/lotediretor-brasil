from __future__ import annotations
import re

PAGE_RE=re.compile(r'(?m)^<<<PAGE:(\d+)>>>\s*$')

def semantic_chunks(text:str,size:int=1800,overlap:int=160):
    """Create page-aware retrieval chunks while preserving paragraph structure.

    Page markers originate from the PDF extractor. Long paragraphs are windowed
    with overlap, but the returned locator remains stable and page-addressable.
    """
    if size < 100: raise ValueError('size must be >= 100')
    if overlap < 0 or overlap >= size: raise ValueError('overlap must satisfy 0 <= overlap < size')
    markers=list(PAGE_RE.finditer(text)); pages=[]
    if markers:
        for i,m in enumerate(markers):
            end=markers[i+1].start() if i+1<len(markers) else len(text)
            pages.append((int(m.group(1)),text[m.end():end]))
    else:
        pages=[(None,text)]
    out=[];idx=0
    for page,body in pages:
        paragraphs=[]
        for raw_para in re.split(r'\n\s*\n+',body):
            cleaned=' '.join(x.strip() for x in raw_para.splitlines() if x.strip()).strip()
            if cleaned:paragraphs.append(cleaned)
        if not paragraphs and body.strip():paragraphs=[' '.join(body.split())]
        buffer=''
        def emit(chunk:str):
            nonlocal idx
            if not chunk.strip():return
            out.append({'index':idx,'text':chunk.strip(),'page_number':page,'locator':f'page:{page}#chunk-{idx}' if page else f'chunk:{idx}'})
            idx+=1
        for para in paragraphs:
            if len(para)>size:
                if buffer:emit(buffer);buffer=''
                pos=0
                while pos<len(para):
                    emit(para[pos:pos+size]);pos+=size-overlap
                continue
            candidate=(buffer+'\n\n'+para).strip() if buffer else para
            if len(candidate)<=size:buffer=candidate
            else:emit(buffer);buffer=para
        if buffer:emit(buffer)
    return out
