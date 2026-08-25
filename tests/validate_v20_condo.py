from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
required=[
    root/'db/platform/migrations/199_v20_condo_operational.sql',
    root/'services/platform-api/src/condo/v20-governance.ts',
    root/'services/platform-api/src/condo/condo-v20.controller.ts',
    root/'services/platform-api/src/condo/condo-v20-ops.controller.ts',
]
for p in required: assert p.exists(),p
text='\n'.join(p.read_text() for p in required)
for token in ['PARSED_CANDIDATES','CONFLICTING','CALCULATED_NOT_ENACTED','BLOCKED_AUTOMATION','READY_FOR_MANUAL_ISSUANCE','CANDIDATE_REVIEW','NO_AUTHORIZED_DOCUMENTS','__NO_DOCUMENT_ACCESS__','FORCE ROW LEVEL SECURITY']:
    assert token in text,token
subprocess.run(['node','tests/test_v20_condo_governance.js'],check=True)
print('v20 Condomínio 360 operational validator OK')
