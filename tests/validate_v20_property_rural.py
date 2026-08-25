from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
required=[
    root/'db/platform/migrations/198_v20_property_rural_operational.sql',
    root/'services/platform-api/src/property360/v20-market.ts',
    root/'services/platform-api/src/property360/property360-v20.controller.ts',
    root/'services/platform-api/src/rural/v20-readiness.ts',
    root/'services/platform-api/src/rural/rural-v20.controller.ts',
]
for p in required:
    assert p.exists(),p
text='\n'.join(p.read_text() for p in required)
for token in ['REQUIRES_CALIBRATION','DEMO_SOURCE_FORBIDDEN','CALCULATED_FROM_APPROVED_METHOD_AND_REAL_EVIDENCE','property360.resolve_b2b_api_key','RURAL_CONNECTOR_CODES','RUNTIME_EVIDENCE_COMPLETE','EXTERNAL_GATES_REMAIN','homologated:false']:
    assert token in text,token
subprocess.run(['node','tests/test_v20_property_rural.js'],check=True)
print('v20 Imovel 360 + RE Rural validator OK')
