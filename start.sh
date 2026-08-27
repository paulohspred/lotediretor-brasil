#!/usr/bin/env sh
set -eu
[ -f .env ] || cp .env.example .env
docker compose up -d --build
printf '\nLoteDiretor v20 pre-homologacao iniciado em http://localhost:8080\n'
