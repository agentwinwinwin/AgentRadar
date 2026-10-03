#!/bin/sh
set -eu

base_url=${BASE_URL:-http://127.0.0.1:8000/api/v1}
frontend_url=${FRONTEND_URL:-http://127.0.0.1:5173/api/v1}
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

for attempt in $(seq 1 40); do
  if curl --fail --silent "$base_url/health/ready" > "$tmp_dir/ready.json"; then break; fi
  sleep 2
done
curl --fail --silent "$base_url/health/live" > /dev/null
curl --fail --silent "$frontend_url/health/ready" > /dev/null
printf '%s\n' 'health=PASS'

smoke_password=$(openssl rand -hex 24)
docker compose exec -T -e SMOKE_PASSWORD="$smoke_password" backend python manage.py shell -c \
  'import os; from django.contrib.auth import get_user_model; u,_=get_user_model().objects.get_or_create(username="sprint15-smoke"); u.set_password(os.environ["SMOKE_PASSWORD"]); u.save()' > /dev/null

curl --fail --silent -H 'Content-Type: application/json' \
  --data "{\"username\":\"sprint15-smoke\",\"password\":\"$smoke_password\"}" \
  "$base_url/auth/login" > "$tmp_dir/login.json"
token=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["token"])' "$tmp_dir/login.json")
auth="Authorization: Token $token"
printf '%s\n' 'authentication=PASS'
curl --fail --silent "$base_url/projects?page=1" > "$tmp_dir/projects.json"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert "results" in d' "$tmp_dir/projects.json"
repository_id=$(docker compose exec -T backend python manage.py shell -c 'from apps.repositories.models import Repository; print(Repository.objects.filter(is_disabled=False).values_list("id",flat=True).first())' | tail -1)
repository_name=$(docker compose exec -T backend python manage.py shell -c "from apps.repositories.models import Repository; print(Repository.objects.get(pk=$repository_id).full_name)" | tail -1)

curl --fail --silent -H "$auth" -H 'Content-Type: application/json' \
  --data "{\"repository_id\":$repository_id}" "$base_url/watchlist" > /dev/null
curl --fail --silent -H "$auth" -H 'Content-Type: application/json' \
  --data "{\"repository_id\":$repository_id}" "$base_url/watchlist" > /dev/null
curl --fail --silent -H "$auth" "$base_url/watchlist" > /dev/null
curl --fail --silent -H "$auth" "$base_url/projects/$repository_id" > /dev/null
printf '%s\n' 'watchlist_and_detail=PASS'

for report_type in DAILY WEEKLY; do
  curl --fail --silent -H "$auth" -H 'Content-Type: application/json' \
    --data "{\"report_type\":\"$report_type\"}" "$base_url/reports" > /dev/null
done
printf '%s\n' 'scheduled_reports=PASS'

docker compose exec -T celery-worker celery -A config call alerts.evaluate_repository_alerts \
  --args "[$repository_id]" > /dev/null
sleep 2
curl --fail --silent -H "$auth" "$base_url/alerts?repository_id=$repository_id" > /dev/null
printf '%s\n' 'celery_and_alerts=PASS'

copilot_status=$(curl --silent --max-time 180 --output "$tmp_dir/copilot.json" --write-out '%{http_code}' -H "$auth" -H 'Content-Type: application/json' \
  --data "{\"message\":\"请用现有证据简要分析 GitHub Repository $repository_name。\"}" \
  "$base_url/copilot/chat")
if [ "$copilot_status" != "200" ]; then
  printf 'copilot_llm=FAIL status=%s ' "$copilot_status"
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("detail") or d.get("message") or "unknown")' "$tmp_dir/copilot.json"
  exit 1
fi
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d.get("answer") and "evidence" in d' "$tmp_dir/copilot.json"
printf '%s\n' 'copilot_llm=PASS'

curl --fail --silent -X POST -H "$auth" "$base_url/auth/logout" > /dev/null
docker compose exec -T backend python manage.py shell -c \
  'from django.contrib.auth import get_user_model; get_user_model().objects.filter(username="sprint15-smoke").delete()' > /dev/null

printf '%s\n' 'production_smoke=PASS' "repository_id=$repository_id" 'token_output=REDACTED'
