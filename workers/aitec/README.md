# A.I TEC compute — v20

O compute avançado permanece isolado em `services/aitec-engine`, enquanto a Platform API controla autorização, tenant, projeto e idempotência. `workers/aitec` executa a fila durável `aitec.job` de forma assíncrona com `FOR UPDATE SKIP LOCKED`, retry limitado e recuperação de jobs abandonados.

O worker chama somente o contrato interno `/aitec/v20/execute/{operation}` e valida que `tenant_id`, `project_id` e `constraint_snapshot_id` devolvidos pelo engine correspondem ao contexto persistido. Resultados continuam classificados como estudo/pré-projeto; a fila não converte solver técnico em projeto executivo ou homologação profissional.
