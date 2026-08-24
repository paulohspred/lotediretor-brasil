import type {UrbanViabilityContext} from './urban-viability';

export type SpatialEvidenceItem={
  feature_id?:string;
  layer_code?:string;
  layer_title?:string;
  domain?:string;
  intersection_area_m2?:number|string|null;
  intersection_ratio?:number|string|null;
  attributes?:Record<string,unknown>|null;
};

export type SpatialContextEvidence={field:keyof UrbanViabilityContext;value:number|boolean|string;featureIds:string[];layerCodes:string[];reason:string};
export type SpatialContextResult={context:Partial<UrbanViabilityContext>;evidence:SpatialContextEvidence[]};

const text=(value:unknown)=>String(value??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase();
const finite=(value:unknown)=>{const n=Number(value);return Number.isFinite(n)?n:null;};
const attr=(item:SpatialEvidenceItem,...keys:string[])=>{const a=item.attributes||{};for(const key of keys){const value=(a as any)[key];if(value!==undefined&&value!==null&&value!=='')return value;}return null;};
const fingerprint=(item:SpatialEvidenceItem)=>text([item.layer_code,item.layer_title,attr(item,'type','tipo','category','categoria','class','classe','subtype','subtipo')].join(' '));

function pushEvidence(out:SpatialContextEvidence[],field:keyof UrbanViabilityContext,value:number|boolean|string,items:SpatialEvidenceItem[],reason:string){
  out.push({field,value,featureIds:[...new Set(items.map(x=>String(x.feature_id||'')).filter(Boolean))],layerCodes:[...new Set(items.map(x=>String(x.layer_code||'')).filter(Boolean))],reason});
}

export function deriveSpatialRuleContext(items:SpatialEvidenceItem[]):SpatialContextResult{
  const context:Partial<UrbanViabilityContext>={};const evidence:SpatialContextEvidence[]=[];
  const intersecting=items.filter(item=>Number(item.intersection_area_m2||0)>0||Number(item.intersection_ratio||0)>0);

  const heritage=intersecting.filter(item=>text(item.domain)==='HERITAGE');
  if(heritage.length){context.heritage_overlap=true;pushEvidence(evidence,'heritage_overlap',true,heritage,'published_heritage_feature_intersects_parcel');}

  const easements=intersecting.filter(item=>/(SERVIDAO|EASEMENT|FAIXA DE SERVIDAO|RIGHT OF WAY)/.test(fingerprint(item)));
  if(easements.length){const value=easements.reduce((sum,item)=>sum+Math.max(0,finite(item.intersection_area_m2)||0),0);context.easement_overlap_m2=value;pushEvidence(evidence,'easement_overlap_m2',value,easements,'published_easement_feature_intersects_parcel');}

  const widening=intersecting.filter(item=>/(MELHORAMENTO|ROAD WIDENING|WIDENING|ALARGAMENTO|ALINHAMENTO PROJETADO|PLANNED ROAD)/.test(fingerprint(item)));
  if(widening.length){const value=widening.reduce((sum,item)=>sum+Math.max(0,finite(item.intersection_area_m2)||0),0);context.road_widening_area_m2=value;pushEvidence(evidence,'road_widening_area_m2',value,widening,'published_road_widening_feature_intersects_parcel');}

  const aerodrome=intersecting.filter(item=>/(AERODROM|DECEA|AIRSPACE|ZONEAMENTO DE RUIDO|PBZPA|PZEA)/.test(fingerprint(item)));
  const limits=aerodrome.map(item=>({item,value:finite(attr(item,'height_limit_m','max_height_m','altura_max_m','limite_altura_m','cota_max_m','max_elevation_m'))})).filter((x):x is {item:SpatialEvidenceItem;value:number}=>x.value!==null&&x.value>=0);
  if(limits.length){const value=Math.min(...limits.map(x=>x.value));context.aerodrome_limit_m=value;pushEvidence(evidence,'aerodrome_limit_m',value,limits.filter(x=>x.value===value).map(x=>x.item),'published_aerodrome_height_limit');}

  const roads=intersecting.filter(item=>text(item.domain)==='MOBILITY'&&/(ROAD|VIA|VIARIO|LOGRADOURO|ALINHAMENTO)/.test(fingerprint(item)));
  const widths=roads.map(item=>({item,value:finite(attr(item,'road_width_m','width_m','largura_m','largura_via_m'))})).filter((x):x is {item:SpatialEvidenceItem;value:number}=>x.value!==null&&x.value>0);
  if(widths.length){const value=Math.max(...widths.map(x=>x.value));context.road_width_m=value;pushEvidence(evidence,'road_width_m',value,widths.filter(x=>x.value===value).map(x=>x.item),'published_road_width_attribute');}

  return{context,evidence};
}
