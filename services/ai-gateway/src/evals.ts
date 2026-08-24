export type RankingMetrics={recallAtK:number|null;mrr:number|null;ndcgAtK:number|null;relevant:number;retrieved:number;firstRelevantRank:number|null};
export type EvalCaseInput={id?:string;expectedStatus?:string;actualStatus?:string;retrievedIds?:string[];relevantEvidenceIds?:string[];answerEvidenceIds?:string[];allowedEvidenceIds?:string[];expectedDecisionStatus?:string;actualDecisionStatus?:string};

function unique(values:any){return [...new Set((Array.isArray(values)?values:[]).map(String).filter(Boolean))];}
function round(value:number){return Number(value.toFixed(6));}

export function rankingMetrics(retrievedInput:any,relevantInput:any,kInput=10):RankingMetrics{
  const retrieved=unique(retrievedInput);const relevant=unique(relevantInput);const k=Math.max(1,Math.min(Number(kInput)||10,100));const top=retrieved.slice(0,k);const rel=new Set(relevant);
  if(!relevant.length)return{recallAtK:null,mrr:null,ndcgAtK:null,relevant:0,retrieved:top.length,firstRelevantRank:null};
  const hits=top.filter(id=>rel.has(id)).length;const first=top.findIndex(id=>rel.has(id));
  let dcg=0;top.forEach((id,index)=>{if(rel.has(id))dcg+=1/Math.log2(index+2);});let idcg=0;for(let i=0;i<Math.min(relevant.length,k);i++)idcg+=1/Math.log2(i+2);
  return{recallAtK:round(hits/relevant.length),mrr:first>=0?round(1/(first+1)):0,ndcgAtK:idcg?round(dcg/idcg):0,relevant:relevant.length,retrieved:top.length,firstRelevantRank:first>=0?first+1:null};
}

export function citationMetrics(answerEvidenceInput:any,allowedEvidenceInput:any){
  const cited=unique(answerEvidenceInput);const allowed=new Set(unique(allowedEvidenceInput));if(!cited.length)return{citationPrecision:null,citations:0,invalidCitationIds:[] as string[]};const invalid=cited.filter(id=>!allowed.has(id));return{citationPrecision:round((cited.length-invalid.length)/cited.length),citations:cited.length,invalidCitationIds:invalid};
}

function average(values:(number|null)[]){const xs=values.filter((x):x is number=>typeof x==='number'&&Number.isFinite(x));return xs.length?round(xs.reduce((a,b)=>a+b,0)/xs.length):null;}

export function evaluateCases(casesInput:any,k=10){
  const cases=(Array.isArray(casesInput)?casesInput:[]) as EvalCaseInput[];
  const results=cases.map((c,index)=>{
    const ranking=rankingMetrics(c.retrievedIds,c.relevantEvidenceIds,k);const citation=citationMetrics(c.answerEvidenceIds,c.allowedEvidenceIds??c.relevantEvidenceIds);
    const expectedStatus=c.expectedStatus?String(c.expectedStatus).toUpperCase():null;const actualStatus=c.actualStatus?String(c.actualStatus).toUpperCase():null;const expectedDecision=c.expectedDecisionStatus?String(c.expectedDecisionStatus).toUpperCase():null;const actualDecision=c.actualDecisionStatus?String(c.actualDecisionStatus).toUpperCase():null;
    return{id:c.id||`case-${index+1}`,expectedStatus,actualStatus,statusPass:expectedStatus&&actualStatus?expectedStatus===actualStatus:null,expectedDecisionStatus:expectedDecision,actualDecisionStatus:actualDecision,decisionPass:expectedDecision&&actualDecision?expectedDecision===actualDecision:null,ranking,citation};
  });
  const statusComparable=results.filter(x=>x.statusPass!==null);const decisionComparable=results.filter(x=>x.decisionPass!==null);const invalidCitations=results.reduce((n,x)=>n+x.citation.invalidCitationIds.length,0);
  return{version:'v20',k,total:results.length,metrics:{recallAtK:average(results.map(x=>x.ranking.recallAtK)),mrr:average(results.map(x=>x.ranking.mrr)),ndcgAtK:average(results.map(x=>x.ranking.ndcgAtK)),citationPrecision:average(results.map(x=>x.citation.citationPrecision)),statusAccuracy:statusComparable.length?round(statusComparable.filter(x=>x.statusPass).length/statusComparable.length):null,decisionAccuracy:decisionComparable.length?round(decisionComparable.filter(x=>x.decisionPass).length/decisionComparable.length):null,invalidCitations},results};
}
