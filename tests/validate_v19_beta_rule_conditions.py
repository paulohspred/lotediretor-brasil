from pathlib import Path
s=Path('services/platform-api/src/territorial/territorial.service.ts').read_text()
helper=Path('services/platform-api/src/territorial/rule-evaluator.ts').read_text()
mig=Path('db/platform/migrations/192_v19_beta_legal_conditions_uses.sql').read_text()
worker=Path('workers/documents/main.py').read_text()
for token in ['evaluateRuleCondition','PENDING_CONTEXT','NOT_APPLICABLE','POTENTIAL_MIN_M2','MAX_HEIGHT_M','unknownRules.length']:
    assert token in s, token
for token in ['lot_area_m2','frontage_m','road_width_m','between','UNKNOWN','legacy extraction metadata']:
    assert token in helper, token
for token in ['extraction_metadata','source_article_id','planning.zone_use_permission']:
    assert token in mig, token
assert "Jsonb(cand.get('condition') or {})" in worker
assert 'extraction_metadata' in worker and 'source_article_id' in worker
print('v19-beta legal rule applicability contracts OK')
