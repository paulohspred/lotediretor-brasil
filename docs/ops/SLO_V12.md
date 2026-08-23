# Initial SLOs — v12

These are release targets, not claims of achieved production performance.

- Platform API availability: 99.9% monthly after GA.
- Control API availability: 99.9% monthly after GA.
- Interactive API p95: < 800 ms excluding long jobs/external providers.
- MVT p95: < 1.5 s at supported zoom/data volume.
- Report jobs: 95% complete within 2 minutes for standard reports.
- Data publication: zero activation when blocking quality checks fail.
- Tenant isolation: zero cross-tenant rows in mandatory release drill.
- RPO: <= 24h initially; RTO: <= 4h initially, tightened after infrastructure drills.
