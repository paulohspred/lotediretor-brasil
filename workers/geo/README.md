# Geo worker — v14

Worker operacional de quality gate espacial. Reavalia snapshots geoespaciais publicados, verificando geometria válida e SRID 4326 nas features carregadas. Falha bloqueante é registrada em `data_quality.result` e rebaixa `validation_status` do snapshot.
