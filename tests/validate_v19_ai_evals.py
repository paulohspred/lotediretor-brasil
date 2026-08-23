import json
from pathlib import Path
p=json.loads(Path('data/ai-evals/golden-v19.json').read_text())
assert p['version']=='19.0.0-rc.3'
assert len(p['cases'])>=3
by={x['id']:x for x in p['cases']}
assert by['grounded-confirmed-rule']['expectedStatus']=='GROUNDED'
assert by['abstain-no-grounding']['expectedStatus']=='ABSTAINED'
assert by['candidate-is-not-grounding']['rules'][0]['status']=='CANDIDATE'
s=Path('ops/ai/run-golden-evals.py').read_text();assert '/ai/v1/evaluate' in s and 'INTERNAL_API_TOKEN' in s
print('v19 AI eval golden-set contract OK')
