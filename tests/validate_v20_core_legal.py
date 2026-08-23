from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
migration = (root / 'db/platform/migrations/197_v20_core_legal_foundation.sql').read_text()
base = (root / 'db/platform/migrations/150_v15_territorial_core.sql').read_text()
uses = (root / 'db/platform/migrations/192_v19_beta_legal_conditions_uses.sql').read_text()
evaluator = (root / 'services/platform-api/src/territorial/rule-evaluator.ts').read_text()
runtime = (root / 'services/platform-api/src/territorial/rule-runtime.ts').read_text()

# Existing canonical legal/territorial base must remain intact.
for token in [
    'CREATE TABLE IF NOT EXISTS legal.relation(',
    'CREATE TABLE IF NOT EXISTS legal.conflict(',
    'CREATE TABLE IF NOT EXISTS analysis.calculation(',
]:
    assert token in base, token
assert 'planning.zone_use_permission' in uses

# v20 adds explicit temporal legal effects and deterministic rule dependencies.
for token in [
    'source_article_id', 'target_article_id', 'SUSPENDE_EFICACIA',
    'RESTAURA_EFICACIA', 'ALTERA', 'REVOGA', 'REGULAMENTA',
    'rule_code', 'rule_family', 'legal_effect', 'hard_constraint',
    'formula', 'input_schema', 'output_schema', 'superseded_by_rule_id',
    'legal.rule_dependency', 'REQUIRES', 'OVERRIDES', 'LIMITS', 'EXCLUDES',
    'planning.rule_binding', 'INSTRUMENT', 'LICENSING_TRIGGER',
    'SPATIAL_RESTRICTION', 'CALCULATION',
]:
    assert token in migration, token

# Applicability stays tri-state and now covers explicit urban/licensing inputs.
for token in ['MATCH', 'NO_MATCH', 'UNKNOWN', 'condition.all', 'condition.any', 'condition.not', 'between', 'eiv_required', 'zeis_code', 'road_widening_area_m2']:
    assert token in evaluator, token

# Precedence/formulas are deterministic; conflicts and missing dependencies are surfaced.
for token in ['evaluateFormula', 'evaluateRuleGraph', 'SAME_PRECEDENCE', 'required_rule_unknown', 'required_rule_not_applicable', 'division_by_zero']:
    assert token in runtime, token

# Guard the product rule: canonical bindings begin as candidates and must be reviewed.
assert "status text NOT NULL DEFAULT 'CANDIDATE'" in migration
assert "CHECK(status IN ('CANDIDATE','CONFIRMED','REJECTED','SUPERSEDED'))" in migration

# Execute the actual TypeScript runtime (transpiled by the project TypeScript compiler)
# rather than treating string assertions as sufficient behavioral evidence.
subprocess.run(['node', str(root / 'tests/test_v20_rule_runtime.js')], cwd=root, check=True)

print('v20 core/legal rule graph contracts OK')
