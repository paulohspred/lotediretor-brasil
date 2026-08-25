export const MUNICIPAL_V20_VERSION='municipality-governance-v20.2';

export const ROLE_PERMISSIONS:Record<string,string[]>= {
  MUNICIPAL_ADMIN:['municipality.manage','department.manage','member.manage','dataset.manage','dataset.read','dataset.publish','dataset.rollback','tax.write','license.review','audit.read','export.create','offboarding.manage','ai.retrieve'],
  DATA_STEWARD:['dataset.manage','dataset.read','dataset.publish','dataset.rollback','audit.read','export.create','ai.retrieve'],
  LEGAL_REVIEWER:['dataset.read','dataset.publish','license.review','audit.read','ai.retrieve'],
  GIS_EDITOR:['dataset.manage','dataset.read','ai.retrieve'],
  TAX_EDITOR:['dataset.read','tax.write','ai.retrieve'],
  LICENSING_AGENT:['dataset.read','license.review','ai.retrieve'],
  AUDITOR:['dataset.read','audit.read','export.create'],
  VIEWER:['dataset.read'],
  AI_USER:['dataset.read','ai.retrieve'],
};

export function effectivePermissions(roles:any[]){
  const out=new Set<string>();
  for(const row of roles||[]){if(String(row?.status||'ACTIVE')!=='ACTIVE')continue;for(const p of ROLE_PERMISSIONS[String(row?.role||'')]||[])out.add(p);for(const p of row?.permission_overrides||[])out.add(String(p));}
  return [...out].sort();
}
export function requirePermission(permissions:string[],permission:string){if(!permissions.includes(permission))throw new Error(`missing_permission:${permission}`);}

export function publicationGate(input:any){
  const status=String(input?.snapshot_status||'').toUpperCase();const action=String(input?.action||'').toUpperCase();const perms=(input?.permissions||[]).map(String);const missing:string[]=[];
  if(!input?.source_snapshot_id)missing.push('source_snapshot_id');
  if(action==='PUBLISH'&&status!=='VALIDATED')missing.push('validated_snapshot');
  if(action==='ROLLBACK'&&status!=='SUPERSEDED')missing.push('previously_published_snapshot');
  if(action==='ROLLBACK'&&!input?.target_snapshot_id)missing.push('target_snapshot_id');
  const required=action==='ROLLBACK'?'dataset.rollback':'dataset.publish';if(!perms.includes(required))missing.push(required);if(!String(input?.actor||'').trim())missing.push('actor');if(!String(input?.reason||'').trim())missing.push('reason');
  return missing.length?{status:'BLOCKED',missing}:{status:'READY',action,policy:'Publication is explicit, audited and reversible; rollback only targets a previously published snapshot.'};
}

export function licensingDecisionGuard(input:any){
  if(input?.automated_decision_requested)return{status:'BLOCKED_AUTOMATION',policy:'Municipal licensing decisions require an authenticated human reviewer.'};
  const missing:string[]=[];if(!(input?.permissions||[]).includes('license.review'))missing.push('license.review');if(!Array.isArray(input?.evidence_ids)||!input.evidence_ids.length)missing.push('evidence_ids');if(!String(input?.reviewer||'').trim())missing.push('reviewer');if(!String(input?.reason||'').trim())missing.push('reason');
  const decision=String(input?.decision||'').toUpperCase();if(!['APPROVED','REJECTED','MORE_INFO'].includes(decision))missing.push('decision');return missing.length?{status:'HUMAN_REVIEW_REQUIRED',missing}:{status:'READY_FOR_HUMAN_RECORD',decision,reviewer:input.reviewer};
}

export function buildInstitutionalAcl(input:any){
  const permissions=(input?.permissions||[]).map(String);if(!permissions.includes('ai.retrieve'))return{status:'FORBIDDEN',source_snapshot_ids:[],dataset_ids:[]};
  const subject=String(input?.subject_id||''),roles=new Set((input?.roles||[]).map(String));const allowed:any[]=[];
  for(const ds of input?.datasets||[]){
    const visibility=String(ds.visibility||'INTERNAL');const grants=Array.isArray(ds.acl)?ds.acl:[];
    const aclAllowed=visibility==='OPEN'||grants.some((g:any)=>String(g.principal_kind)==='SUBJECT'&&String(g.principal_value)===subject&&(g.permissions||[]).includes('READ'))||grants.some((g:any)=>String(g.principal_kind)==='ROLE'&&roles.has(String(g.principal_value))&&(g.permissions||[]).includes('READ'));
    if(aclAllowed&&String(ds.snapshot_status)==='PUBLISHED'&&ds.source_snapshot_id)allowed.push(ds);
  }
  return{status:'READY',municipality_ibge:String(input?.municipality_ibge||''),dataset_ids:allowed.map(x=>String(x.id)),source_snapshot_ids:[...new Set(allowed.map(x=>String(x.source_snapshot_id)))],policy:'RBAC and dataset ACL are resolved before retrieval; no authorized snapshot means no retrieval.'};
}

export function openDataProjection(dataset:any,snapshot:any){
  if(String(dataset?.visibility)!=='OPEN'||String(dataset?.status)!=='ACTIVE'||String(snapshot?.status)!=='PUBLISHED')return{status:'NOT_PUBLIC'};
  return{status:'PUBLIC',dataset_code:dataset.dataset_code,title:dataset.title,kind:dataset.kind,base_date:snapshot.base_date,source_snapshot_id:snapshot.source_snapshot_id,checksum_manifest:snapshot.checksum_manifest||{},published_at:snapshot.published_at};
}

export function exportManifest(input:any){
  const datasets=(input?.datasets||[]).map((x:any)=>({dataset_code:x.dataset_code,kind:x.kind,visibility:x.visibility,status:x.status})).sort((a:any,b:any)=>a.dataset_code.localeCompare(b.dataset_code));
  return{schema_version:MUNICIPAL_V20_VERSION,municipality_ibge:String(input?.municipality_ibge||''),generated_at:String(input?.generated_at||''),datasets,counts:input?.counts||{},includes:['governance','datasets','published_snapshot_pointers','tax','licensing','audit_metadata'],excludes:['authentication_secrets','provider_credentials']};
}
