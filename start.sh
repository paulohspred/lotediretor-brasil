#!/usr/bin/env sh
set -eu

[ -f .env ] || cp .env.example .env
export COMPOSE_PROFILES="${COMPOSE_PROFILES:-full}"

printf 'Validando topologia Docker Compose...\n'
docker compose config >/dev/null

printf 'Construindo e iniciando LoteDiretor (profiles: %s)...\n' "$COMPOSE_PROFILES"
docker compose up -d --build

printf 'Aguardando readiness dos serviços...\n'
./ops/runtime/wait-healthy.sh "${STARTUP_TIMEOUT_SECONDS:-420}"

printf 'Executando smoke test do runtime...\n'
./ops/runtime/smoke.sh

printf '\nLoteDiretor v20 pre-homologacao operacional em http://localhost:8080\n'
printf 'Observacao: runtime local aprovado não equivale a homologacao de producao.\n'
