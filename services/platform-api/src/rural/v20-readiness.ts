export const RURAL_CONNECTOR_CODES=[
  'CAR','SIGEF','SNCR','CCIR','CAFIR_CIB','IBAMA','PRODES','DETER','FUNAI','CNUC','INCRA_ASSENTAMENTOS','QUILOMBOLAS','SICOR_BACEN'
] as const;

export type RuralConnectorEvidence={
  code:string;
  registry_status?:string|null;
  access_mode?:string|null;
  legal_availability?:string|null;
  source_id?:string|null;
  run_status?:string|null;
  source_snapshot_id?:string|null;
  source_sha256?:string|null;
  source_date?:string|null;
  validation_status?:string|null;
  snapshot_status?:string|null;
  publication_status?:string|null;
  license_terms?:string|null;
  completed_at?:string|null;
};

export function connectorReadiness(row:RuralConnectorEvidence){
  const missing:string[]=[];
  if(!RURAL_CONNECTOR_CODES.includes(String(row.code).toUpperCase() as any))missing.push('known_connector_code');
  if(String(row.registry_status||'').toUpperCase()!=='CONFIGURED')missing.push('registry_status_CONFIGURED');
  if(!String(row.access_mode||'').trim())missing.push('access_mode');
  if(!String(row.legal_availability||'').trim())missing.push('legal_availability');
  if(!String(row.source_id||'').trim())missing.push('source_id');
  if(String(row.run_status||'').toUpperCase()!=='SUCCEEDED')missing.push('successful_runtime_run');
  if(!String(row.source_snapshot_id||'').trim())missing.push('source_snapshot_id');
  if(!/^[a-f0-9]{64}$/i.test(String(row.source_sha256||'')))missing.push('source_sha256');
  if(!String(row.source_date||'').trim())missing.push('source_date');
  if(String(row.validation_status||'').toUpperCase()!=='PASS')missing.push('validation_status_PASS');
  if(String(row.publication_status||'').toUpperCase()!=='ACTIVE')missing.push('publication_status_ACTIVE');
  if(!String(row.license_terms||'').trim())missing.push('license_terms');
  if(!String(row.completed_at||'').trim())missing.push('completed_at');
  return {
    code:String(row.code).toUpperCase(),
    status:missing.length?'EXTERNAL_GATE':'RUNTIME_EVIDENCE_COMPLETE',
    runtime_evidence_complete:missing.length===0,
    homologated:false,
    missing,
    policy:'Runtime/source evidence is necessary but does not by itself assert legal ownership, registry equivalence or professional homologation.',
  };
}

export function readinessMatrix(rows:RuralConnectorEvidence[]){
  const byCode=new Map((rows||[]).map(r=>[String(r.code).toUpperCase(),r]));
  const items=RURAL_CONNECTOR_CODES.map(code=>connectorReadiness(byCode.get(code)||{code}));
  return {status:items.every(x=>x.runtime_evidence_complete)?'RUNTIME_EVIDENCE_COMPLETE':'EXTERNAL_GATES_REMAIN',items,homologated:false};
}

export function recordGoldenReview(input:{expected:any;actual:any;reviewer?:string|null;professional_reference?:string|null;reviewed_at?:string|null}){
  const hasReview=Boolean(String(input.reviewer||'').trim()&&String(input.professional_reference||'').trim()&&String(input.reviewed_at||'').trim());
  return {
    status:hasReview?'EXTERNAL_REVIEW_RECORDED':'PENDING_EXTERNAL_REVIEW',
    matches:JSON.stringify(input.expected)===JSON.stringify(input.actual),
    homologated:false,
    missing:hasReview?[]:['reviewer','professional_reference','reviewed_at'],
    policy:'Recorded review evidence is auditable but professional credentials and external truth remain outside automated code validation.',
  };
}
