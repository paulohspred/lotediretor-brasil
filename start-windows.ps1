if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
Write-Host "LoteDiretor v7 iniciado em http://localhost:8080"
