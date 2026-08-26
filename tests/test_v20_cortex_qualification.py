from pathlib import Path

root=Path(__file__).resolve().parents[1]
harness=(root/'ops/cortex/qualify-local.sh').read_text()
report=(root/'ops/cortex/qualification-report.py').read_text()
manifest=(root/'ops/cortex/evidence-manifest.py').read_text()
security=(root/'ops/security/runtime-baseline.sh').read_text()

required=[
 'production_parity','staging_parity','immutable_release','rollback_contract',
 'compose_model','build_images','stack_health','runtime_smoke','aitec_runtime',
 'rls_isolation','privacy_lgpd','municipality_factory','ai_retrieval',
 'critical_fixture_seed','browser_critical','security_baseline','load_profile',
 'fault_injection','observability','backup','restore_dr',
]
for gate in required:
    assert f'run_gate {gate} ' in harness, f'harness does not ledger gate {gate}'
    assert repr(gate) in report or f"'{gate}'" in report, f'report does not require gate {gate}'

for needle in [
 'qualification-report.py','evidence-manifest.py','gate-status.tsv',
 'production-parity.json','staging-parity.json','immutable-release.json','rollback-contract.txt',
 'Final qualification report rejected a nominal PASS','full qualification will be rejected',
]:
    assert needle in harness, f'harness missing final-report contract: {needle}'

for needle in ['ops/security/supply-chain.py','supply-chain.json','sbom.cdx.json','supply_chain_inventory']:
    assert needle in security, f'security baseline missing supply-chain evidence: {needle}'

for needle in [
 'production_parity','staging_parity','immutable_release','rollback_contract',
 'playwright-results.json','k6-summary.json','security_baseline','supply_chain_inventory','cyclonedx_sbom','observability_gate',
 'LOCAL_SUPPLY_CHAIN_INVENTORY_NOT_VULNERABILITY_SCAN','vulnerability_image_signature_scan',
 'dr_evidence','opensearch_health','ld-ai-b-leak.json',
 "'productionHomologated':False",
 'STRUCTURAL_STAGING_PARITY_CONTRACT_NOT_DEPLOYED_STAGING_EVIDENCE',
 'independent_pentest','production_like_staging','live_canary_rollback','production_ha_dr',
 'official_sources_and_providers','professional_institutional_review','main_branch_protection',
 'NOT_HOMOLOGATED',
]:
    assert needle in report, f'qualification report missing evidence/final gate: {needle}'

assert 'productionHomologated remains false' in manifest
print('v20 Cortex local + release/staging/supply-chain evidence report contract OK')
