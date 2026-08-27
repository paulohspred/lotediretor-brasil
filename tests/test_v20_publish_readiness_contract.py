from pathlib import Path

root=Path(__file__).resolve().parents[1]
source=(root/'ops/cortex/publish-readiness.py').read_text()

for needle in [
    "REQUIRED_PROFILES = ('ci', 'soak', 'capacity')",
    'qualification-report.json',
    'evidence-manifest.json',
    "localQualificationStatus') != 'PASS'",
    "productionHomologated') is not False",
    "qualificationStatus') != 'PASS'",
    "git.get('dirty') is not False",
    'Cortex profile evidence comes from different commits',
    'current HEAD does not match qualified commit',
    'production-homologation.py',
    "'readyToMergeDevelop': local_ready",
    "'readyToPublishProduction': local_ready and production_ready",
    "'productionHomologated': local_ready and production_ready",
    '--require-local',
    '--require-production',
    '--self-test',
]:
    assert needle in source, f'publish readiness missing fail-closed contract: {needle}'

print('v20 Cortex publish readiness contract OK')
