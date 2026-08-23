from pathlib import Path
s=Path('services/platform-api/src/territorial/territorial.service.ts').read_text()
h=Path('services/platform-api/src/territorial/rule-evaluator.ts').read_text()
for n in ["r.zone_code=$2::text or r.zone_code is null",'conflictedRuleIds',"'LEGAL_CONFLICT'","'CONFLICTING'","status=conflicts.length||unknownRules.length?'NEEDS_REVIEW'",'rawRuleValue','normalizeRuleNumber']:
    assert n in s,n
assert "if(conflictedRuleIds.has(String(rule.id)))continue" in s
for n in ["u==='%'","u==='percent'","u==='pct'","raw/100"]:
    assert n in h,n
print('v19 territorial conflict/normalization safety OK')
