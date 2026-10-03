#!/bin/sh
set -eu

dump_file=${1:?usage: verify_restore.sh DUMP_FILE}
test_db=agentradar_restore_verify
source_db=${POSTGRES_DB:-agentradar}
db_user=${POSTGRES_USER:-agentradar}
if [ "$source_db" = "$test_db" ]; then
  echo 'restore target must differ from source' >&2
  exit 2
fi

cleanup() {
  docker compose exec -T postgres dropdb --if-exists --username "$db_user" "$test_db" >/dev/null
}
trap cleanup EXIT
cleanup
docker compose exec -T postgres createdb --username "$db_user" "$test_db"
docker compose exec -T postgres pg_restore --username "$db_user" --dbname "$test_db" --no-owner < "$dump_file"

for table in repositories repository_snapshots repository_activity_metrics repository_trend_scores repository_potential_scores ml_models knowledge_documents watchlists alerts; do
  source_count=$(docker compose exec -T postgres psql --username "$db_user" --dbname "$source_db" -tAc "SELECT count(*) FROM $table")
  restored_count=$(docker compose exec -T postgres psql --username "$db_user" --dbname "$test_db" -tAc "SELECT count(*) FROM $table")
  if [ "$source_count" != "$restored_count" ]; then
    echo "count mismatch: $table" >&2
    exit 1
  fi
  printf '%s=%s\n' "$table" "$restored_count"
done
printf '%s\n' 'restore_verification=PASS'
