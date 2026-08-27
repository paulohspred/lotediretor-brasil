const fs=require('fs');
const os=require('os');
const path=require('path');
const assert=require('assert');
const ts=require('typescript');

const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'services/ai-gateway/src/telemetry.ts'),'utf8');
const main=fs.readFileSync(path.join(root,'services/ai-gateway/src/main.ts'),'utf8');
const prometheus=fs.readFileSync(path.join(root,'infra/prometheus/prometheus.yml'),'utf8');
const observability=fs.readFileSync(path.join(root,'ops/observability/runtime-gate.sh'),'utf8');
const slo=fs.readFileSync(path.join(root,'docs/ops/SLO.md'),'utf8');

const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'ld-ai-telemetry-v20-'));
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
const output=path.join(tmp,'telemetry.js');
fs.writeFileSync(output,compiled);
delete process.env.OTEL_EXPORTER_OTLP_ENDPOINT;
const telemetry=require(output);

const traceId='0123456789abcdef0123456789abcdef';
const parentSpan='0123456789abcdef';
const req={
  method:'POST',url:'/ai/v1/retrieve?tenant=must-not-be-a-label',
  headers:{traceparent:`00-${traceId}-${parentSpan}-01`},
  routeOptions:{url:'/ai/v1/retrieve'},
};
const reply={statusCode:200};
const state=telemetry.beginHttpTrace(req);
assert.equal(state.traceId,traceId,'valid incoming trace id must be continued');
assert.match(telemetry.traceparent(state),new RegExp(`^00-${traceId}-[0-9a-f]{16}-01$`));
telemetry.finishHttpTrace('ai-gateway','test',req,reply);
const metrics=telemetry.renderHttpMetrics('ai-gateway');
assert(metrics.includes('lotediretor_http_requests_total{service="ai-gateway",method="POST",status_class="2xx"} 1'));
assert(metrics.includes('lotediretor_http_request_duration_seconds_count{service="ai-gateway",method="POST",status_class="2xx"} 1'));
assert(!/tenant|project|job_id|document_id|url_path|route=/.test(metrics),'RED metric labels must remain low-cardinality');

for(const needle of [
  "from './telemetry.js'",
  "app.addHook('onRequest'",
  "app.addHook('onResponse'",
  "app.get('/metrics'",
  "finishHttpTrace('ai-gateway',VERSION",
  "reply.header('x-trace-id'",
])assert(main.includes(needle),`AI Gateway main missing telemetry contract: ${needle}`);

for(const needle of ["job_name: ai-gateway","targets: ['ai-gateway:3003']"])
  assert(prometheus.includes(needle),`Prometheus missing AI Gateway scrape: ${needle}`);
for(const needle of ["'ai-gateway'","ai_gateway_red_metrics_missing_or_empty","lotediretor_http_requests_total{service=\"ai-gateway\"}"])
  assert(observability.includes(needle),`Observability gate missing AI Gateway RED proof: ${needle}`);
for(const needle of ['`ai-gateway`','lotediretor_http_request_duration_seconds','A.I TEC — fila assíncrona'])
  assert(slo.includes(needle),`SLO missing telemetry scope: ${needle}`);

console.log('v20 AI Gateway low-cardinality RED + trace propagation contract OK');
