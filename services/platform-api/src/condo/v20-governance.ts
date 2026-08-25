export const CONDO_V20_VERSION='condo-governance-v20.1';

export type LayoutBlock={page:number;block_id:string;text:string;bbox?:number[]|null};
export function parseClauseLayout(documentId:string,blocks:LayoutBlock[]){
  if(!documentId)throw new Error('document_id_required');
  const sorted=[...(blocks||[])].sort((a,b)=>a.page-b.page||String(a.block_id).localeCompare(String(b.block_id)));
  const clauses:any[]=[];let current:any=null;
  const heading=/^\s*((?:art\.?|artigo|cl[aá]usula|cap[ií]tulo|se[cç][aã]o)\s*[\w.-]+|\d+(?:\.\d+)*[.)-])\s*/i;
  for(const b of sorted){
    if(!Number.isInteger(b.page)||b.page<1||!String(b.block_id||'').trim()||!String(b.text||'').trim())continue;
    const text=String(b.text).trim();const match=text.match(heading);
    if(match||!current){
      current={id:`${documentId}:clause:${clauses.length+1}`,locator:match?match[1]:`PAGE-${b.page}-BLOCK-${b.block_id}`,status:'CANDIDATE',text:'',citations:[]};clauses.push(current);
    }
    current.text=(current.text?current.text+'\n':'')+text;
    current.citations.push({page:b.page,block_id:b.block_id,bbox:b.bbox||null});
  }
  return{status:'PARSED_CANDIDATES',parser_version:CONDO_V20_VERSION,document_id:documentId,clauses,policy:'Parser preserves page/block citations; extracted clauses remain CANDIDATE until human confirmation.'};
}

function atDate(value:string|undefined|null){return value?Date.parse(String(value).slice(0,10)+'T00:00:00Z'):null;}
export function resolveRuleSet(rules:any[],asOf:string){
  const t=atDate(asOf);if(t==null||Number.isNaN(t))throw new Error('invalid_as_of');
  const active=(rules||[]).filter(r=>{
    if(String(r.status).toUpperCase()!=='CONFIRMED'||!Number.isFinite(Number(r.precedence)))return false;
    const from=atDate(r.effective_from),to=atDate(r.effective_to);
    return (from==null||from<=t)&&(to==null||to>t);
  });
  const groups=new Map<string,any[]>();for(const r of active){const key=String(r.parameter||'');if(!key)continue;groups.set(key,[...(groups.get(key)||[]),r]);}
  const resolved:any[]=[];const conflicts:any[]=[];
  for(const [parameter,items] of groups){const top=Math.max(...items.map(x=>Number(x.precedence)));const winners=items.filter(x=>Number(x.precedence)===top);const values=new Set(winners.map(x=>JSON.stringify(x.value)));
    if(values.size>1)conflicts.push({parameter,status:'CONFLICTING',precedence:top,rule_ids:winners.map(x=>x.id),reason:'same_explicit_precedence_different_values'});
    else resolved.push({parameter,status:'CONFIRMED',precedence:top,rule:winners[0]});
  }
  return{status:conflicts.length?'CONFLICTING':'RESOLVED',as_of:asOf,active_rule_count:active.length,resolved,conflicts,policy:'Precedence is caller/data supplied; the engine does not invent legal hierarchy.'};
}

export function evaluateBallot(input:any){
  const eligible=new Set((input?.eligible_subject_hashes||[]).map(String));const q=input?.quorum||{};
  for(const k of ['min_present','min_participation_fraction','min_approval_fraction'])if(!Number.isFinite(Number(q[k])))return{status:'REQUIRES_INPUT',missing:[`quorum.${k}`]};
  const accepted:any[]=[];const rejected:any[]=[];const seen=new Set<string>();
  for(const vote of input?.votes||[]){const subject=String(vote.subject_hash||''),choice=String(vote.choice||'').toUpperCase();const reasons:string[]=[];if(!eligible.has(subject))reasons.push('NOT_ELIGIBLE');if(seen.has(subject))reasons.push('DUPLICATE_VOTE');if(!['FOR','AGAINST','ABSTAIN'].includes(choice))reasons.push('INVALID_CHOICE');if(String(vote.signature_status||'').toUpperCase()!=='VERIFIED')reasons.push('SIGNATURE_NOT_VERIFIED');if(reasons.length)rejected.push({subject_hash:subject,reasons});else{seen.add(subject);accepted.push({subject_hash:subject,choice});}}
  const present=accepted.length,forCount=accepted.filter(x=>x.choice==='FOR').length,against=accepted.filter(x=>x.choice==='AGAINST').length,abstain=accepted.filter(x=>x.choice==='ABSTAIN').length;const participation=eligible.size?present/eligible.size:0;const decisive=forCount+against;const approval=decisive?forCount/decisive:0;
  const quorumMet=present>=Number(q.min_present)&&participation>=Number(q.min_participation_fraction);const approved=quorumMet&&approval>=Number(q.min_approval_fraction);
  return{status:'CALCULATED_NOT_ENACTED',quorum_met:quorumMet,approved,present,eligible:eligible.size,for_count:forCount,against_count:against,abstain_count:abstain,participation_fraction:Number(participation.toFixed(6)),approval_fraction:Number(approval.toFixed(6)),rejected,policy:'Ballot calculation never enacts a decision or sanction; enactment requires the recorded governance workflow.'};
}

export function sanctionGuard(input:any){
  const missing:string[]=[];if(String(input?.rule_status||'').toUpperCase()!=='CONFIRMED')missing.push('confirmed_rule');if(!Array.isArray(input?.evidence_ids)||!input.evidence_ids.length)missing.push('evidence_ids');
  if(input?.automated_decision_requested)return{status:'BLOCKED_AUTOMATION',missing,policy:'Sanctions cannot be automatically decided or issued.'};
  if(missing.length)return{status:'BLOCKED_MISSING_GROUNDS',missing};
  const decision=String(input?.human_decision||'').toUpperCase();if(!['APPROVE','REJECT'].includes(decision))return{status:'HUMAN_REVIEW_REQUIRED',missing:['human_decision']};
  if(!String(input?.human_reviewer||'').trim()||!String(input?.decision_reason||'').trim())return{status:'HUMAN_REVIEW_REQUIRED',missing:['human_reviewer','decision_reason']};
  const defense=String(input?.defense_status||'').toUpperCase();if(!['RESOLVED','WAIVED_WITH_EVIDENCE'].includes(defense))return{status:'DEFENSE_DUE_PROCESS_REQUIRED',missing:['resolved_or_evidenced_waiver']};
  return{status:decision==='APPROVE'?'READY_FOR_MANUAL_ISSUANCE':'REJECTED_BY_HUMAN_REVIEW',decision,reviewer:input.human_reviewer,policy:'READY_FOR_MANUAL_ISSUANCE is not ISSUED; billing/notification is a separate explicit action.'};
}

export function legalChangeDiff(before:any[],after:any[]){
  const b=new Map((before||[]).map(x=>[String(x.id),x])),a=new Map((after||[]).map(x=>[String(x.id),x]));const events:any[]=[];
  for(const [id,row] of a){if(!b.has(id))events.push({kind:'ADDED',rule_id:id,after:row,status:'CANDIDATE_REVIEW'});else if(JSON.stringify(b.get(id))!==JSON.stringify(row))events.push({kind:'CHANGED',rule_id:id,before:b.get(id),after:row,status:'CANDIDATE_REVIEW'});}
  for(const [id,row] of b)if(!a.has(id))events.push({kind:'REMOVED',rule_id:id,before:row,status:'CANDIDATE_REVIEW'});
  return{status:events.length?'CHANGES_DETECTED':'NO_CHANGE',events,policy:'Detected changes are alerts for review, not automatically confirmed legal changes.'};
}

export function buildExternalSummary(input:any){
  const rules=(input?.rules||[]).filter((r:any)=>String(r.status).toUpperCase()==='CONFIRMED').map((r:any)=>({id:r.id,parameter:r.parameter,value:r.value,source_locator:r.source_locator,evidence_ids:r.evidence_ids||[]}));
  return{status:'SHAREABLE_SUMMARY',mode:String(input?.mode||'BUYER').toUpperCase(),condominium:{id:input?.condominium?.id,name:input?.condominium?.name,municipality_ibge:input?.condominium?.municipality_ibge},rules,property_id:input?.property_id||null,aitec_project_id:input?.aitec_project_id||null,redacted:['unit_owners','private_contacts','private_documents','votes_identity','sanction_defense_private_text'],policy:'External view only exposes confirmed rule summaries and explicit integration references.'};
}

export function buildRetrievalAcl(tenantId:string,condominiumId:string,documentIds:string[]){
  if(!tenantId||!condominiumId)throw new Error('tenant_and_condominium_required');const ids=[...new Set((documentIds||[]).map(String).filter(Boolean))];
  return{tenant_id:tenantId,condominium_id:condominiumId,allowed_document_ids:ids,opensearch_filter:{bool:{filter:[{term:{tenant_id:tenantId}},{term:{domain:'condo'}},{term:{condominium_id:condominiumId}},{terms:{document_id:ids.length?ids:['__NO_DOCUMENT_ACCESS__']}}]}},policy:'ACL filter must be applied before retrieval; an empty document ACL matches no documents.'};
}
