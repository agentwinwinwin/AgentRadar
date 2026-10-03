#!/bin/sh
set -eu

backup_dir=${1:?usage: backup_postgres.sh BACKUP_DIRECTORY}
mkdir -p "$backup_dir"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
docker compose exec -T postgres pg_dump \
  --username "${POSTGRES_USER:-agentradar}" \
  --dbname "${POSTGRES_DB:-agentradar}" \
  --format=custom > "$backup_dir/agentradar-$stamp.dump"
printf '%s\n' "$backup_dir/agentradar-$stamp.dump"
