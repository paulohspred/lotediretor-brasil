import http from 'k6/http';import {check,sleep} from 'k6';
export const options={stages:[{duration:'30s',target:10},{duration:'60s',target:25},{duration:'30s',target:0}],thresholds:{http_req_failed:['rate<0.01'],http_req_duration:['p(95)<800']}};
const base=__ENV.BASE_URL||'http://localhost:8080';
export default function(){const r=http.get(`${base}/api/v1/health`);check(r,{'health 200':x=>x.status===200});sleep(1)}
