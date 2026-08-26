import http from 'k6/http';
import {check,sleep} from 'k6';

const profile=__ENV.LOAD_PROFILE||'ci';
const profiles={
  ci:[
    {duration:'10s',target:5},
    {duration:'20s',target:10},
    {duration:'10s',target:0},
  ],
  soak:[
    {duration:'2m',target:25},
    {duration:'10m',target:25},
    {duration:'2m',target:0},
  ],
  capacity:[
    {duration:'2m',target:25},
    {duration:'3m',target:50},
    {duration:'3m',target:75},
    {duration:'2m',target:0},
  ],
};

if(!profiles[profile])throw new Error(`unknown LOAD_PROFILE=${profile}`);

export const options={
  stages:profiles[profile],
  thresholds:{
    http_req_failed:['rate<0.01'],
    http_req_duration:['p(95)<1500','p(99)<3000'],
    'http_req_duration{endpoint:ai-retrieve}':['p(95)<2000','p(99)<3500'],
    'http_req_duration{endpoint:solar-energy}':['p(95)<1500','p(99)<3000'],
    'http_req_duration{endpoint:aitec-terrain}':['p(95)<1500','p(99)<3000'],
    checks:['rate>0.99'],
  },
  userAgent:'LoteDiretor-k6-v20',
};

const base=(__ENV.BASE_URL||'http://127.0.0.1:8080').replace(/\/$/,'');
const internalToken=__ENV.INTERNAL_API_TOKEN||'';
const loadTenant=__ENV.LOAD_AI_TENANT_ID||'0198f020-0000-7000-8000-000000000001';
const internalHeaders={'X-Internal-Token':internalToken,'Content-Type':'application/json'};

function get(path,name,headers={}){
  const response=http.get(`${base}${path}`,{headers,tags:{endpoint:name}});
  check(response,{[`${name} status`]:r=>r.status>=200&&r.status<400});
  return response;
}

function post(path,name,payload,headers={}){
  const response=http.post(`${base}${path}`,JSON.stringify(payload),{headers:{'Content-Type':'application/json',...headers},tags:{endpoint:name}});
  check(response,{[`${name} status`]:r=>r.status>=200&&r.status<300});
  return response;
}

function jsonBody(response){try{return response.json()}catch{return null}}

export default function(){
  get('/','site-home');
  get('/api/v1/health','platform-health');
  get('/control/v1/health','control-health');
  get('/ai/health','ai-health');
  get('/solar/health','solar-health');
  get('/aitec/health','aitec-health');

  if(internalToken){
    const caps=get('/aitec/v20/capabilities','aitec-capabilities',{'X-Internal-Token':internalToken});
    check(caps,{'aitec capability contract':r=>r.body.includes('STUDY_PREPROJECT_NOT_EXECUTIVE')});

    const terrain=post('/aitec/v20/execute/terrain.tin','aitec-terrain',{
      kwargs:{samples:[
        {x:0,y:0,z:100},{x:10,y:0,z:101},{x:0,y:10,z:102},{x:10,y:10,z:103},
      ]},
      context:{tenant_id:loadTenant,project_id:'load-test-project',seed:42},
    },internalHeaders);
    const terrainJson=jsonBody(terrain);
    check(terrain,{
      'aitec terrain executed':()=>terrainJson?.status==='EXECUTED',
      'aitec terrain calculated':()=>terrainJson?.result?.status==='CALCULATED'&&Number(terrainJson?.result?.triangle_count||0)>=2,
    });

    const solar=post('/solar/v20/execute/energy.irradiance','solar-energy',{
      kwargs:{
        dc_kwp:10,
        monthly_poa_kwh_m2:[100,100,100,100,100,100,100,100,100,100,100,100],
        loss_fractions:{temperature:0.02,soiling:0.02,shading:0.02,mismatch:0.02,wiring:0.02,inverter:0.02,availability:0.02},
      },
    },internalHeaders);
    const solarJson=jsonBody(solar);
    check(solar,{
      'solar energy executed':()=>solarJson?.status==='EXECUTED',
      'solar energy calculated':()=>solarJson?.result?.status==='CALCULATED_FROM_EXPLICIT_IRRADIANCE_AND_LOSSES'&&Number(solarJson?.result?.annual_net_kwh||0)>0,
    });

    const retrieval=post('/ai/v1/retrieve','ai-retrieve',{
      tenantId:loadTenant,
      query:'ALFA URBANO coeficiente máximo 3.2',
      scope:{domains:['runtime-ai'],includePublic:false,knowledgeStatuses:['CONFIRMED'],topK:10},
    },internalHeaders);
    const retrievalJson=jsonBody(retrieval);
    check(retrieval,{
      'AI retrieval contract':()=>retrievalJson?.status==='OK'&&Array.isArray(retrievalJson?.items),
      'AI retrieval tenant context preserved':()=>String(retrievalJson?.tenantId||loadTenant)===loadTenant,
    });
  }
  sleep(0.25);
}
