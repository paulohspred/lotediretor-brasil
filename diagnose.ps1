docker compose ps
Write-Host "--- Platform API ---"
try { Invoke-RestMethod http://localhost:8080/api/v1/health | ConvertTo-Json } catch { Write-Host $_ }
Write-Host "--- Control API ---"
try { Invoke-RestMethod http://localhost:8080/control/v1/health | ConvertTo-Json } catch { Write-Host $_ }
Write-Host "--- Logs Platform ---"
docker compose logs platform-api --tail=100

Write-Host "--- Martin / tiles ---"
try { Invoke-WebRequest http://localhost:8080/tiles/catalog -UseBasicParsing | Select-Object StatusCode } catch { Write-Host $_ }
Write-Host "--- Workers ---"
docker compose ps document-worker report-worker billing-worker data-pipelines martin solar-engine aitec-engine ai-gateway
