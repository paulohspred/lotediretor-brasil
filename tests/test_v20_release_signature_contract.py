from pathlib import Path

root=Path(__file__).resolve().parents[1]
verify=(root/'ops/release/verify-signatures.sh').read_text()
gate=(root/'ops/release/gate.sh').read_text()

for needle in [
    'ghcr.io/sigstore/cosign/cosign:v3.1.3',
    'COSIGN_PUBLIC_KEY',
    'COSIGN_CERTIFICATE_IDENTITY',
    'COSIGN_CERTIFICATE_OIDC_ISSUER',
    'slsaprovenance1',
    'verify-attestation',
    'image@sha256',
    'REGISTRY_SIGNATURE_AND_SLSA_PROVENANCE_VERIFIED',
    '--self-test',
]:
    assert needle in verify, f'missing release signature/provenance contract: {needle}'

assert 'v3.1.2' not in verify, 'known-vulnerable Cosign v3.1.2 must not be pinned'
assert 'legacy' not in verify.lower() or '--bundle' not in verify, 'legacy bundle verification must not be introduced'

for needle in [
    'verify-signatures.sh --self-test',
    'VERIFY_RELEASE_SIGNATURES',
    'DEPLOY_ENVIRONMENT',
    'staging|production',
    'requires VERIFY_RELEASE_SIGNATURES=true',
    'verify-signatures.sh',
]:
    assert needle in gate, f'release gate is not fail-closed for signed target artifacts: {needle}'

print('v20 release signature + SLSA provenance contract OK')
