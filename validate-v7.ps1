$ErrorActionPreference = "Stop"
python tests/test_solar_domain.py
python tests/test_aitec_domain.py
python tests/validate_v7_contracts.py
Write-Host "v7 domain/contract validation OK"
Write-Host "For full validation run: npm install; npm run typecheck; npm run build; docker compose up -d --build"
