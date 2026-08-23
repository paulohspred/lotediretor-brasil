from pathlib import Path
import json,sys,yaml
R=Path(__file__).resolve().parents[1];compose=(R/'docker-compose.yml').read_text();pm=(R/'services/platform-api/src/main.ts').read_text()
checks={'version_v12':(R/'VERSION').read_text().strip()=='v12','otel_native':(R/'services/platform-api/src/telemetry.ts').exists() and 'traceparent' in pm,'otel_collector':'otel-collector:' in compose,'tempo':'tempo:' in compose,'loki':'loki:' in compose,'promtail':'promtail:' in compose,'alertmanager':'alertmanager:' in compose,'alert_rules':(R/'infra/prometheus/rules/lotediretor.yml').exists(),'pdf_test':(R/'tests/test_report_renderer_v12.py').exists(),'release_gate':(R/'ops/release/gate.sh').exists(),'slo':(R/'docs/ops/SLO_V12.md').exists()}
print(json.dumps(checks,indent=2));bad=[k for k,v in checks.items() if not v]
if bad:print('FAILED',bad,file=sys.stderr);sys.exit(1)
