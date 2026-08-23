#!/usr/bin/env sh
set -eu
[ -f .env ] || cp .env.example .env
docker compose up -d --build
printf '
LoteDiretor v7 iniciado em http://localhost:8080
'
