from pathlib import Path
m=Path('services/ai-gateway/src/main.ts').read_text()
for token in ("risk==='HIGH'&&decisive&&!confirmed.length",'high_risk_requires_confirmed_deterministic_rule',"professional_review:'OBRIGATORIA'",'confirmedRules(rules)'):
    assert token in m,token
# Provider synthesis must not run as an unrestricted free-form decision path.
assert m.index('confirmedRules(rules)') < m.index("high_risk_requires_confirmed_deterministic_rule")
print('v19-rc high-risk AI deterministic-rule gate OK')
