docker compose ps
Write-Host "--- Platform API ---"
try { Invoke-RestMethod http://localhost:8080/api/v1/health | ConvertTo-Json } catch { Write-Host $_ }
Write-Host "--- Control API ---"
try { Invoke-RestMethod http://localhost:8080/control/v1/health | ConvertTo-Json } catch { Write-Host $_ }
Write-Host "--- Logs Platform ---"
docker compose logs platform-api --tail=100

Write-Host "--- Martin / tiles ---"
try { Invoke-WebRequest http://localhost:8080/tiles/catalog -UseBasicParsing | Select-Object StatusCode } catch { Write-Host $_ }
Write-Host "--- Core services / workers ---"
docker compose ps platform-api control-api ai-gateway solar-engine aitec-engine martin geo-worker document-worker report-worker rural-monitor-worker rural-export-worker billing-worker data-pipelines event-dispatcher aitec-worker
