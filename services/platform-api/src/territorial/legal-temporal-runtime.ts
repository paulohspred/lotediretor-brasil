export type LegalTemporalState='ACTIVE'|'INACTIVE'|'UNKNOWN'|'CONFLICTING';

export type LegalVersion={
  id:string;
  document_id?:string|null;
  valid_from?:string|Date|null;
  valid_to?:string|Date|null;
  status?:string|null;
};

export type LegalRelation={
  id:string;
  from_document_version_id:string;
  to_document_version_id:string;
  source_article_id?:string|null;
  target_article_id?:string|null;
  relation_type:'ALTERA'|'REVOGA'|'REGULAMENTA'|'CONSOLIDA'|'SUSPENDE_EFICACIA'|'RESTAURA_EFICACIA'|'CORRIGE'|'REFERENCIA'|'SUBSTITUI'|'OTHER'|string;
  valid_from?:string|Date|null;
  valid_to?:string|Date|null;
  status?:string|null;
};

export type LegalTemporalEvent={
  relationId:string;
  relationType:string;
  sourceVersionId:string;
  targetVersionId:string;
  targetArticleId:string|null;
  effectiveAt:string|null;
  stateEffect:'NONE'|'OFF'|'SUSPEND'|'RESTORE'|'UNKNOWN';
};

export type LegalScopeResult={
  key:string;
  versionId:string;
  articleId:string|null;
  state:LegalTemporalState;
  reasons:string[];
  eventIds:string[];
};

export type LegalTemporalResult={
  asOf:string;
  versions:Record<string,LegalScopeResult>;
  articles:Record<string,LegalScopeResult>;
  events:LegalTemporalEvent[];
  pendingRelationIds:string[];
  unknownRelationIds:string[];
  conflicts:Array<{scopeKey:string;relationIds:string[];reason:string}>;
};

const EFFECT_TYPES=new Set(['REVOGA','SUBSTITUI','SUSPENDE_EFICACIA','RESTAURA_EFICACIA']);

function time(value:string|Date|null|undefined){
  if(value===undefined||value===null||value==='')return null;
  const n=value instanceof Date?value.getTime():Date.parse(String(value));
  return Number.isFinite(n)?n:null;
}

function iso(value:string|Date|null|undefined){const n=time(value);return n===null?null:new Date(n).toISOString();}

function withinWindow(from:string|Date|null|undefined,to:string|Date|null|undefined,at:number){
  const start=time(from),end=time(to);
  return (start===null||start<=at)&&(end===null||at<end);
}

function baseState(version:LegalVersion,at:number):LegalScopeResult{
  const invalidFrom=version.valid_from!=null&&time(version.valid_from)===null;
  const invalidTo=version.valid_to!=null&&time(version.valid_to)===null;
  if(invalidFrom||invalidTo)return{key:`version:${version.id}`,versionId:version.id,articleId:null,state:'UNKNOWN',reasons:['invalid_version_validity'],eventIds:[]};
  if(!withinWindow(version.valid_from,version.valid_to,at))return{key:`version:${version.id}`,versionId:version.id,articleId:null,state:'INACTIVE',reasons:['outside_version_validity'],eventIds:[]};
  return{key:`version:${version.id}`,versionId:version.id,articleId:null,state:'ACTIVE',reasons:['inside_version_validity'],eventIds:[]};
}

function scopeKey(versionId:string,articleId:string|null|undefined){return articleId?`article:${articleId}`:`version:${versionId}`;}

function effect(type:string):LegalTemporalEvent['stateEffect']{
  switch(type){
    case 'REVOGA':case 'SUBSTITUI':return 'OFF';
    case 'SUSPENDE_EFICACIA':return 'SUSPEND';
    case 'RESTAURA_EFICACIA':return 'RESTORE';
    default:return 'NONE';
  }
}

export function resolveLegalTemporalGraph(versions:LegalVersion[],relations:LegalRelation[],asOf:string|Date):LegalTemporalResult{
  const at=time(asOf);if(at===null)throw new Error('invalid_as_of');
  const asOfIso=new Date(at).toISOString();
  const versionResults:Record<string,LegalScopeResult>={};
  const articleResults:Record<string,LegalScopeResult>={};
  const versionById=new Map(versions.map(v=>[v.id,v]));
  for(const version of versions)versionResults[version.id]=baseState(version,at);

  const events:LegalTemporalEvent[]=[];
  const pendingRelationIds:string[]=[];
  const unknownRelationIds:string[]=[];
  const conflicts:LegalTemporalResult['conflicts']=[];
  const byScope=new Map<string,Array<{relation:LegalRelation;at:number;effect:LegalTemporalEvent['stateEffect']}>>();

  for(const relation of relations){
    if(relation.status!=='CONFIRMED'){pendingRelationIds.push(relation.id);continue;}
    if(!versionById.has(relation.to_document_version_id)){unknownRelationIds.push(relation.id);continue;}
    const relAt=time(relation.valid_from);
    const relType=String(relation.relation_type||'').toUpperCase();
    const stateEffect=effect(relType);
    const event:LegalTemporalEvent={relationId:relation.id,relationType:relType,sourceVersionId:relation.from_document_version_id,targetVersionId:relation.to_document_version_id,targetArticleId:relation.target_article_id||null,effectiveAt:iso(relation.valid_from),stateEffect};
    events.push(event);
    if(stateEffect==='NONE')continue;
    if(relAt===null){unknownRelationIds.push(relation.id);continue;}
    if(relAt>at)continue;
    const relEnd=time(relation.valid_to);
    if(relation.valid_to!=null&&relEnd===null){unknownRelationIds.push(relation.id);continue;}
    // REVOGA/SUBSTITUI remain terminal after their effective date. Suspension/restoration
    // relations can themselves have a validity window and are only considered while active.
    if((stateEffect==='SUSPEND'||stateEffect==='RESTORE')&&relEnd!==null&&at>=relEnd)continue;
    const key=scopeKey(relation.to_document_version_id,relation.target_article_id);
    byScope.set(key,[...(byScope.get(key)||[]),{relation,at:relAt,effect:stateEffect}]);
  }

  for(const [key,items] of byScope){
    const sample=items[0].relation;
    const articleId=sample.target_article_id||null;
    const base=versionResults[sample.to_document_version_id]||{key:`version:${sample.to_document_version_id}`,versionId:sample.to_document_version_id,articleId:null,state:'UNKNOWN' as const,reasons:['missing_target_version'],eventIds:[]};
    const target:LegalScopeResult=articleId?{key,versionId:sample.to_document_version_id,articleId,state:base.state,reasons:[...base.reasons],eventIds:[]}:{...base,key,reasons:[...base.reasons],eventIds:[...base.eventIds]};
    const ordered=[...items].sort((a,b)=>a.at-b.at||a.relation.id.localeCompare(b.relation.id));
    const byInstant=new Map<number,typeof ordered>();
    for(const item of ordered)byInstant.set(item.at,[...(byInstant.get(item.at)||[]),item]);
    let terminalOff=false;
    let suspended=false;
    let conflicting=false;
    for(const instant of [...byInstant.keys()].sort((a,b)=>a-b)){
      const group=byInstant.get(instant)!;
      const effects=new Set(group.map(x=>x.effect));
      const ids=group.map(x=>x.relation.id);
      target.eventIds.push(...ids);
      if((effects.has('SUSPEND')&&effects.has('RESTORE'))||(effects.has('OFF')&&effects.has('RESTORE'))){
        conflicts.push({scopeKey:key,relationIds:ids,reason:'opposed_confirmed_effects_same_instant'});conflicting=true;continue;
      }
      if(effects.has('OFF')){terminalOff=true;suspended=false;target.reasons.push(`terminal_off:${ids.join(',')}`);continue;}
      if(effects.has('SUSPEND')){if(!terminalOff){suspended=true;target.reasons.push(`suspended:${ids.join(',')}`);}continue;}
      if(effects.has('RESTORE')){
        if(terminalOff){conflicts.push({scopeKey:key,relationIds:ids,reason:'restore_after_terminal_revocation'});conflicting=true;}
        else{suspended=false;target.reasons.push(`restored:${ids.join(',')}`);}
      }
    }
    if(conflicting)target.state='CONFLICTING';
    else if(terminalOff||suspended)target.state='INACTIVE';
    else target.state=base.state;
    if(articleId)articleResults[articleId]=target;else versionResults[target.versionId]=target;
  }

  // A confirmed state-changing relation with no effective timestamp means the target
  // cannot be safely declared active, even though the relation is not executable yet.
  for(const relationId of unknownRelationIds){
    const relation=relations.find(r=>r.id===relationId);if(!relation||relation.status!=='CONFIRMED'||!EFFECT_TYPES.has(String(relation.relation_type).toUpperCase()))continue;
    const key=scopeKey(relation.to_document_version_id,relation.target_article_id);
    if(relation.target_article_id){
      const base=articleResults[relation.target_article_id]||{key,versionId:relation.to_document_version_id,articleId:relation.target_article_id,state:versionResults[relation.to_document_version_id]?.state||'UNKNOWN',reasons:[],eventIds:[]};
      base.state='UNKNOWN';base.reasons.push(`unknown_effective_time:${relationId}`);base.eventIds.push(relationId);articleResults[relation.target_article_id]=base;
    }else if(versionResults[relation.to_document_version_id]){
      versionResults[relation.to_document_version_id].state='UNKNOWN';versionResults[relation.to_document_version_id].reasons.push(`unknown_effective_time:${relationId}`);versionResults[relation.to_document_version_id].eventIds.push(relationId);
    }
  }

  return{asOf:asOfIso,versions:versionResults,articles:articleResults,events,pendingRelationIds:[...new Set(pendingRelationIds)],unknownRelationIds:[...new Set(unknownRelationIds)],conflicts};
}
