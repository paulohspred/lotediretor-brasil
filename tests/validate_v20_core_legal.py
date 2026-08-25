from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
migration = (root / 'db/platform/migrations/197_v20_core_legal_foundation.sql').read_text()
base = (root / 'db/platform/migrations/150_v15_territorial_core.sql').read_text()
uses = (root / 'db/platform/migrations/192_v19_beta_legal_conditions_uses.sql').read_text()
evaluator = (root / 'services/platform-api/src/territorial/rule-evaluator.ts').read_text()
runtime = (root / 'services/platform-api/src/territorial/rule-runtime.ts').read_text()
viability = (root / 'services/platform-api/src/territorial/urban-viability.ts').read_text()
temporal = (root / 'services/platform-api/src/territorial/legal-temporal-runtime.ts').read_text()
spatial_context = (root / 'services/platform-api/src/territorial/spatial-context.ts').read_text()
analysis_v20 = (root / 'services/platform-api/src/territorial/analysis-v20.service.ts').read_text()
controller = (root / 'services/platform-api/src/territorial/territorial.controller.ts').read_text()

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

# Viability must not turn unknown/conflicting legal inputs into a positive answer and
# explicitly handles the spatial hard constraints required by the Blueprint.
for token in ['buildUrbanViability', 'CONFLICTING', 'PROHIBITED', 'UNKNOWN', 'USE_PERMISSION', 'EIV_TRIGGER', 'OUTORGA_COST', 'AFFORDABLE_HOUSING_SHARE_MIN', 'AERODROME_HEIGHT_MAX_M', 'HERITAGE_RESTRICTION', 'EASEMENT_NO_BUILD', 'ROAD_WIDENING_RESTRICTION']:
    assert token in viability, token

# Positive published spatial evidence may enrich legal context, but absence is never
# silently converted into a false/negative fact when source coverage is unknown.
for token in ['deriveSpatialRuleContext', 'heritage_overlap', 'easement_overlap_m2', 'road_widening_area_m2', 'aerodrome_limit_m', 'road_width_m']:
    assert token in spatial_context, token
assert 'deriveSpatialRuleContext' in analysis_v20
assert 'spatialContextEvidence' in analysis_v20

# Temporal legal effects remain explicit, article-aware and fail closed when dates conflict/are missing.
for token in ['resolveLegalTemporalGraph', 'SUSPENDE_EFICACIA', 'RESTAURA_EFICACIA', 'REVOGA', 'SUBSTITUI', 'opposed_confirmed_effects_same_instant', 'unknown_effective_time']:
    assert token in temporal, token

# POST /analysis must compose resolver -> spatial evidence -> legal temporal graph -> rule graph -> viability decision,
# persist calculation/evidence memory and use a new idempotency contract.
for token in ['resolveLegalTemporalGraph', 'evaluateRuleGraph', 'buildUrbanViability', 'planning.rule_binding', 'planning.zone_use_permission', 'analysis.calculation', 'analysis.snapshot_ref', 'OVERALL_VIABILITY', 'deriveAnalysisRunStatus', 'SPATIAL_CONTEXT']:
    assert token in analysis_v20, token
assert "'analysis.v20'" in controller
assert 'analysisV20.analysisWithClient' in controller
assert 'decisionStatus' in controller

# Guard the product rule: canonical bindings begin as candidates and must be reviewed.
assert "status text NOT NULL DEFAULT 'CANDIDATE'" in migration
assert "CHECK(status IN ('CANDIDATE','CONFIRMED','REJECTED','SUPERSEDED'))" in migration

# Execute the actual TypeScript runtimes (transpiled by the project TypeScript compiler)
# rather than treating string assertions as sufficient behavioral evidence.
subprocess.run(['node', str(root / 'tests/test_v20_rule_runtime.js')], cwd=root, check=True)
subprocess.run(['node', str(root / 'tests/test_v20_urban_viability.js')], cwd=root, check=True)
subprocess.run(['node', str(root / 'tests/test_v20_spatial_context.js')], cwd=root, check=True)
subprocess.run(['node', str(root / 'tests/test_v20_spatial_viability.js')], cwd=root, check=True)
subprocess.run(['node', str(root / 'tests/test_v20_legal_temporal_runtime.js')], cwd=root, check=True)
subprocess.run(['node', str(root / 'tests/test_v20_analysis_policy.js')], cwd=root, check=True)
subprocess.run(['node', str(root / 'tests/test_v20_core_legal_golden.js')], cwd=root, check=True)

print('v20 core/legal temporal, spatial constraints, urban viability, golden corpus and analysis integration contracts OK')
