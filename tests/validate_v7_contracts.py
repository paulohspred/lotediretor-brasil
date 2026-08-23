from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
checks={
 'version_v7': (ROOT/'VERSION').read_text().strip()=='v7',
 'v7_platform_migration': (ROOT/'db/platform/migrations/100_v7_70_percent.sql').exists(),
 'v7_control_migration': (ROOT/'db/control/migrations/030_v7_ops_security.sql').exists(),
 'dataset_contract': 'source.dataset_contract' in (ROOT/'db/platform/migrations/100_v7_70_percent.sql').read_text(),
 'quality_gate': 'data_quality.result' in (ROOT/'db/platform/migrations/100_v7_70_percent.sql').read_text(),
 'publication_rollback': 'ROLLBACK' in (ROOT/'services/platform-api/src/v7.controller.ts').read_text(),
 'ibge_raw_s3': 'put_object' in (ROOT/'workers/data-pipelines/main.py').read_text(),
 'rural_sources_not_faked': 'CONFIGURED_NOT_INGESTED' in (ROOT/'docs/data/SOURCE_INTEGRATION_STATUS.md').read_text(),
 'solar_financials': 'lcoe_brl_per_kwh' in (ROOT/'services/solar-engine/app/domain.py').read_text(),
 'aitec_hard_invalid': 'hard_invalid' in (ROOT/'services/aitec-engine/app/domain.py').read_text(),
 'ai_abstains': 'ABSTAIN' in (ROOT/'services/ai-gateway/src/main.ts').read_text(),
 'entitlement_guard': "module_not_entitled" in (ROOT/'services/platform-api/src/v7.controller.ts').read_text(),
 'admin_readiness': 'ops/readiness' in (ROOT/'services/control-api/src/v7.controller.ts').read_text(),
 'security_headers': 'X-Content-Type-Options' in (ROOT/'infra/caddy/Caddyfile').read_text(),
 'report_artifact': 'report.artifact' in (ROOT/'workers/reports/main.py').read_text(),
 'trusted_ai_grounding': 'safeBody={assistant' in (ROOT/'services/platform-api/src/app.module.ts').read_text() and 'server-grounded' in (ROOT/'apps/client-web/components/workspaces/AiChatBox.tsx').read_text(),
 'generic_geojson_connector': 'sync_geojson_source' in (ROOT/'workers/data-pipelines/connectors.py').read_text(),
 'geo_quality_worker': (ROOT/'workers/geo/main.py').exists(),
 'opensearch_indexer': (ROOT/'workers/ai-ingest/main.py').exists(),
 'aitec_pareto_export': 'export-geojson' in (ROOT/'services/platform-api/src/v7.controller.ts').read_text(),
 'solar_design_sun': 'solar/engine/design' in (ROOT/'services/platform-api/src/app.module.ts').read_text(),
 'maker_checker_effect': 'APPROVAL_EXECUTED' in (ROOT/'services/control-api/src/app.module.ts').read_text(),
}
print(json.dumps(checks,ensure_ascii=False,indent=2))
failed=[k for k,v in checks.items() if not v]
if failed:
 print('FAILED:',','.join(failed),file=sys.stderr);sys.exit(1)
