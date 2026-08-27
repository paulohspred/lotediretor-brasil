if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
Write-Host "LoteDiretor v20 pre-homologacao iniciado em http://localhost:8080"
