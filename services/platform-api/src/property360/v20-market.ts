export type SourceEvidence={
  validation_status?:string|null;
  publication_status?:string|null;
  license_terms?:string|null;
  source_sha256?:string|null;
  source_snapshot_id?:string|null;
  source_date?:string|null;
};

export type Comparable=SourceEvidence&{
  id:string;
  area_m2:number|string;
  price_cents:number|string;
  source_kind?:string|null;
  observed_at?:string|null;
};

export type AvmMethodology={
  version:string;
  status:string;
  min_comparables:number;
  max_age_days:number;
};

function n(v:unknown){const x=Number(v);if(!Number.isFinite(x))throw new Error('non_finite_numeric_input');return x;}
function median(values:number[]){const v=[...values].sort((a,b)=>a-b);if(!v.length)throw new Error('median_requires_values');const m=Math.floor(v.length/2);return v.length%2?v[m]:(v[m-1]+v[m])/2;}
function daysBetween(a:string,b:string){return Math.floor((Date.parse(a.slice(0,10)+'T00:00:00Z')-Date.parse(b.slice(0,10)+'T00:00:00Z'))/86400000);}

export function sourceEvidenceReady(x:SourceEvidence){
  const missing:string[]=[];
  if(String(x.validation_status||'').toUpperCase()!=='PASS')missing.push('validation_status_PASS');
  if(String(x.publication_status||'').toUpperCase()!=='ACTIVE')missing.push('publication_status_ACTIVE');
  if(!String(x.license_terms||'').trim())missing.push('license_terms');
  if(!/^[a-f0-9]{64}$/i.test(String(x.source_sha256||'')))missing.push('source_sha256');
  if(!String(x.source_snapshot_id||'').trim())missing.push('source_snapshot_id');
  if(!String(x.source_date||'').trim())missing.push('source_date');
  return {ready:missing.length===0,missing};
}

export function estimateAvm(areaM2:number,comparables:Comparable[],methodology:AvmMethodology,baseDate:string){
  if(!(areaM2>0))throw new Error('area_m2_must_be_positive');
  if(!/^\d{4}-\d{2}-\d{2}$/.test(baseDate))throw new Error('base_date_must_be_yyyy_mm_dd');
  if(String(methodology.status).toUpperCase()!=='APPROVED')return {status:'REQUIRES_CALIBRATION',methodology_version:methodology.version};
  if(!(methodology.min_comparables>=1)||!(methodology.max_age_days>=0))throw new Error('invalid_methodology_thresholds');
  const rejected:any[]=[];const eligible:any[]=[];
  for(const c of comparables||[]){
    const reasons:string[]=[];
    if(String(c.source_kind||'').toUpperCase()==='DEMO')reasons.push('DEMO_SOURCE_FORBIDDEN');
    const evidence=sourceEvidenceReady(c);reasons.push(...evidence.missing);
    if(!c.observed_at)reasons.push('observed_at');
    else{
      const age=daysBetween(baseDate,String(c.observed_at));
      if(age<0)reasons.push('future_observation');
      else if(age>methodology.max_age_days)reasons.push('observation_too_old');
    }
    const area=n(c.area_m2),price=n(c.price_cents);
    if(area<=0||price<=0)reasons.push('invalid_area_or_price');
    if(reasons.length)rejected.push({id:c.id,reasons});
    else eligible.push({...c,price_per_m2_cents:price/area});
  }
  if(eligible.length<methodology.min_comparables)return {status:'REQUIRES_INPUT',missing:['eligible_real_comparables'],eligible_count:eligible.length,required_count:methodology.min_comparables,rejected};
  const rates=eligible.map(x=>x.price_per_m2_cents);
  const center=median(rates);const deviations=rates.map(x=>Math.abs(x-center));const mad=median(deviations);
  const estimate=Math.round(areaM2*center);const low=Math.max(0,Math.round(areaM2*(center-mad)));const high=Math.round(areaM2*(center+mad));
  return {
    status:'CALCULATED_FROM_APPROVED_METHOD_AND_REAL_EVIDENCE',methodology_version:methodology.version,base_date:baseDate,
    area_m2:areaM2,estimate_cents:estimate,uncertainty_cents:{low,high,median_absolute_deviation_per_m2_cents:Math.round(mad)},
    comparable_ids:eligible.map(x=>x.id),source_snapshot_ids:[...new Set(eligible.map(x=>x.source_snapshot_id).filter(Boolean))],
    evidence:{eligible_count:eligible.length,rejected},
  };
}

export type MarketSeriesRow={
  period:string;
  units_sold?:number|null;
  inventory_end?:number|null;
  units_leased?:number|null;
  rental_inventory_end?:number|null;
  units_launched?:number|null;
  asking_price_cents_m2?:number|null;
  asking_rent_cents_m2?:number|null;
  source_snapshot_id?:string|null;
};

export function marketVelocity(rows:MarketSeriesRow[]){
  const items=(rows||[]).map(row=>{
    const sales=row.units_sold==null?null:n(row.units_sold),stock=row.inventory_end==null?null:n(row.inventory_end);
    const leases=row.units_leased==null?null:n(row.units_leased),rentStock=row.rental_inventory_end==null?null:n(row.rental_inventory_end);
    const saleOffer=sales==null||stock==null?null:sales+stock;const rentalOffer=leases==null||rentStock==null?null:leases+rentStock;
    return {...row,
      vso:saleOffer&&saleOffer>0?Number((sales!/saleOffer).toFixed(6)):null,
      rental_absorption:rentalOffer&&rentalOffer>0?Number((leases!/rentalOffer).toFixed(6)):null,
      formulas:{vso:'units_sold/(units_sold+inventory_end)',rental_absorption:'units_leased/(units_leased+rental_inventory_end)'},
    };
  });
  return {status:items.length?'CALCULATED_FROM_OBSERVED_SERIES':'NOT_AVAILABLE',items};
}

export type WeightedObjective={weight:number;direction:'MAX'|'MIN'};
export function rankLandCandidates(candidates:any[],objectives:Record<string,WeightedObjective>){
  const entries=Object.entries(objectives||{}).filter(([,v])=>Number(v.weight)>0);
  if(!entries.length)throw new Error('positive_objective_weight_required');
  const total=entries.reduce((s,[,v])=>s+Number(v.weight),0);if(!(total>0))throw new Error('positive_objective_weight_required');
  const complete=(candidates||[]).filter(c=>!c.hard_invalid&&entries.every(([metric])=>c.metrics?.[metric]!=null&&Number.isFinite(Number(c.metrics[metric]))));
  const excluded=(candidates||[]).filter(c=>!complete.includes(c)).map(c=>({id:c.id,reasons:c.hard_invalid?['hard_invalid']:entries.filter(([m])=>c.metrics?.[m]==null||!Number.isFinite(Number(c.metrics[m]))).map(([m])=>`missing:${m}`)}));
  const ranges=new Map<string,{min:number,max:number}>();for(const [m] of entries){const vals=complete.map(c=>Number(c.metrics[m]));ranges.set(m,{min:Math.min(...vals),max:Math.max(...vals)});}
  const ranked=complete.map(c=>{let score=0;const contributions:any[]=[];for(const [metric,spec] of entries){const value=Number(c.metrics[metric]);const r=ranges.get(metric)!;const norm=r.max===r.min?1:(value-r.min)/(r.max-r.min);const utility=spec.direction==='MIN'?1-norm:norm;const contribution=utility*(Number(spec.weight)/total);score+=contribution;contributions.push({metric,value,direction:spec.direction,normalized_utility:Number(utility.toFixed(6)),weight:Number(spec.weight),contribution:Number(contribution.toFixed(6))});}return {id:c.id,score:Number(score.toFixed(6)),contributions,metrics:c.metrics};}).sort((a,b)=>b.score-a.score||String(a.id).localeCompare(String(b.id)));
  return {status:ranked.length?'RANKED':'NO_COMPLETE_CANDIDATES',items:ranked,excluded,policy:'Missing weighted metrics and hard-invalid candidates are excluded, never imputed.'};
}
