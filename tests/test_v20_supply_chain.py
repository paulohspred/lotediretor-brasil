from pathlib import Path

root=Path(__file__).resolve().parents[1]
ci=(root/'docker-compose.ci.yml').read_text()
prod=(root/'docker-compose.production.yml').read_text()
scanner=(root/'ops/security/supply-chain.py').read_text()

for text,label in [(ci,'CI'),(prod,'production')]:
    assert 'minio/minio:RELEASE.2025-07-23T15-54-02Z' in text, f'{label} MinIO server must use confirmed official release tag'
    assert 'minio/mc:RELEASE.2025-08-13T08-35-41Z' in text, f'{label} MinIO client must use confirmed official release tag'
    assert 'minio/minio:latest' not in text, f'{label} must not use floating MinIO server tag'
    assert 'minio/mc:latest' not in text, f'{label} must not use floating MinIO client tag'

for needle in [
    "floating_tags={'latest'",
    'owned release artifact is not digest pinned',
    'unapproved MinIO mirror detected',
    "'bomFormat':'CycloneDX'",
    "'specVersion':'1.5'",
    'package-lock.json',
    "rglob('requirements*.txt')",
    "rglob('Dockerfile')",
    'LOCAL_SUPPLY_CHAIN_INVENTORY_NOT_VULNERABILITY_SCAN',
    "OUT/'sbom.cdx.json'",
    "OUT/'supply-chain.json'",
]:
    assert needle in scanner, f'supply-chain contract missing: {needle}'

for mirror in ('cloudpirates/','coollabsio/','derklaro/','sourcemation/'):
    assert mirror in scanner, f'unapproved mirror guard missing: {mirror}'

print('v20 supply-chain inventory + official pinned MinIO contract OK')
