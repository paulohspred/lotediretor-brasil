from pathlib import Path

root=Path(__file__).resolve().parents[1]
harness=(root/'ops/cortex/qualify-local.sh').read_text()
report=(root/'ops/cortex/qualification-report.py').read_text()
manifest=(root/'ops/cortex/evidence-manifest.py').read_text()
security=(root/'ops/security/runtime-baseline.sh').read_text()
redteam=(root/'ops/security/ai-redteam-runtime.sh').read_text()
trivy=(root/'ops/security/trivy-scan.sh').read_text()

required=[
 'production_parity','staging_parity','immutable_release','rollback_contract','signature_contract',
 'compose_model','build_images','security_trivy','stack_health','runtime_smoke','aitec_runtime',
 'rls_isolation','privacy_lgpd','municipality_factory','ai_retrieval','ai_redteam_runtime',
 'critical_fixture_seed','browser_critical','security_baseline','load_profile',
 'fault_injection','observability','backup','restore_dr',
]
for gate in required:
    assert f'run_gate {gate} ' in harness, f'harness does not ledger gate {gate}'
    assert repr(gate) in report or f"'{gate}'" in report, f'report does not require gate {gate}'

for needle in [
 'qualification-report.py','evidence-manifest.py','gate-status.tsv',
 'production-parity.json','staging-parity.json','immutable-release.json','rollback-contract.txt','signature-contract.txt',
 'verify-signatures.sh --self-test','CORTEX_TRIVY','TRIVY_SCAN_IMAGES=1','full qualification will be rejected',
 'Final qualification report rejected a nominal PASS',
]:
    assert needle in harness, f'harness missing final-report/security/release contract: {needle}'

for needle in ['ops/security/supply-chain.py','supply-chain.json','sbom.cdx.json','supply_chain_inventory']:
    assert needle in security, f'security baseline missing supply-chain evidence: {needle}'

for needle in [
 'aquasec/trivy:0.73.0','vuln,misconfig,secret','HIGH,CRITICAL','TRIVY_SCAN_IMAGES',
 'AUTOMATED_VULNERABILITY_SCAN_NOT_INDEPENDENT_PENTEST',
]:
    assert needle in trivy, f'Trivy gate missing contract: {needle}'

for needle in [
 'providerConfigured=false','retrieved_prompt_injection','high_risk_without_confirmed_rule',
 'cross_tenant_private_secret','write_tool_explicit_action',
 'LOCAL_DETERMINISTIC_AI_REDTEAM_NOT_INDEPENDENT_PENTEST_OR_PROVIDER_REDTEAM',
]:
    assert needle in redteam, f'AI runtime redteam missing contract: {needle}'

for needle in [
 'production_parity','staging_parity','immutable_release','rollback_contract','signature_contract','security_trivy',
 'signature_provenance_contract','Cosign signature + SLSA provenance fail-closed contract present',
 'playwright-results.json','k6-summary.json','security_baseline','trivy_scan','trivy-fs.json',
 'ai_runtime_redteam','supply_chain_inventory','cyclonedx_sbom','observability_gate',
 'AUTOMATED_VULNERABILITY_SCAN_NOT_INDEPENDENT_PENTEST','release_image_signature_provenance','Cosign v3.1.3',
 'LOCAL_DETERMINISTIC_AI_REDTEAM_NOT_INDEPENDENT_PENTEST_OR_PROVIDER_REDTEAM','provider_specific_ai_redteam',
 'LOCAL_SUPPLY_CHAIN_INVENTORY_NOT_VULNERABILITY_SCAN',
 'dr_evidence','opensearch_health','ld-ai-b-leak.json',
 "'productionHomologated':False",
 'STRUCTURAL_STAGING_PARITY_CONTRACT_NOT_DEPLOYED_STAGING_EVIDENCE',
 'independent_pentest','production_like_staging','live_canary_rollback','production_ha_dr',
 'official_sources_and_providers','professional_institutional_review','main_branch_protection',
 'NOT_HOMOLOGATED',
]:
    assert needle in report, f'qualification report missing evidence/final gate: {needle}'

assert 'productionHomologated remains false' in manifest
print('v20 Cortex local + release/signature/staging/supply-chain/Trivy/AI-redteam evidence report contract OK')
