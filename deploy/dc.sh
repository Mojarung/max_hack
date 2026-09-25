#!/bin/sh
# docker compose на сервере: базовый файл + MinIO из bitnamilegacy (minio/minio убран с Docker Hub) + HTTPS (Caddy).
#   ./deploy/dc.sh build api   # один образ бэкенда на api/bot/worker/mcp: собирать через api, иначе сборки конфликтуют
#   ./deploy/dc.sh up -d
#   ./deploy/dc.sh logs -f bot
cd "$(dirname "$0")/.." && exec docker compose -p kuzya -f compose.yaml -f compose.override.yaml -f compose.https.yaml "$@"
