#!/bin/sh
set -eu

backup_dir=${1:?usage: backup_artifacts.sh BACKUP_DIRECTORY}
mkdir -p "$backup_dir"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
docker compose run --rm --no-deps backend \
  tar -C /ml -czf - artifacts > "$backup_dir/model-artifacts-$stamp.tar.gz"
printf '%s\n' "$backup_dir/model-artifacts-$stamp.tar.gz"
