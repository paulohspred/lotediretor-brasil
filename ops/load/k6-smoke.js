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
    checks:['rate>0.99'],
  },
  userAgent:'LoteDiretor-k6-v20',
};

const base=(__ENV.BASE_URL||'http://127.0.0.1:8080').replace(/\/$/,'');
const internalToken=__ENV.INTERNAL_API_TOKEN||'';

function get(path,name,headers={}){
  const response=http.get(`${base}${path}`,{headers,tags:{endpoint:name}});
  check(response,{[`${name} status`]:r=>r.status>=200&&r.status<400});
  return response;
}

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
  }
  sleep(0.25);
}
