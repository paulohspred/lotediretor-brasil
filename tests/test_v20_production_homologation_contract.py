from pathlib import Path
import json

root=Path(__file__).resolve().parents[1]
gate=(root/'ops/release/production-homologation.py').read_text()
security=(root/'ops/security/production-security-gate.sh').read_text()
template=json.loads((root/'docs/ops/PRODUCTION_HOMOLOGATION_EVIDENCE.example.json').read_text())

required=[
 'independent_pentest','provider_specific_ai_redteam','production_like_staging',
 'release_image_signature_provenance','live_canary_rollback','production_ha_dr',
 'official_sources_and_providers','professional_institutional_review','main_branch_protection',
]
for name in required:
    assert name in gate, f'homologation gate missing {name}'
    assert name in template['gates'], f'evidence template missing {name}'
    assert template['gates'][name]['status']=='PENDING', f'template must not pre-approve {name}'

for needle in [
 'lotediretor-production-homologation-v1','candidateCommit','releaseImages','@sha256:','DIGEST_RE.fullmatch',
 'productionHomologated must be true','gate not PASS','gate missing evidenceRef','gate missing owner',
 'non-production evidence classification','approval.approvedBy','approval.changeTicket','--self-test',
]:
    assert needle in gate, f'homologation validation missing fail-closed contract: {needle}'

for needle in ['production-homologation.py --self-test','PRODUCTION_HOMOLOGATED','PRODUCTION_HOMOLOGATION_EVIDENCE','production-homologation.py']:
    assert needle in security, f'production security gate missing homologation enforcement: {needle}'

assert template['productionHomologated'] is False
assert template['releaseImages']==[]
print('v20 production homologation evidence contract OK')
