#!/usr/bin/env bash
# Waits for a comic job on the given project to be done or failed, printing each change.
cd /c/Users/tumom/Hackathons/Panelwise || exit 1
q() { docker compose -p panelwise exec -T postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -AtF ' | ' -c \"$1\"" < /dev/null 2>/dev/null; }
last=""
until false; do
  row="$(q "select j.state, coalesce(j.stage,'-'), j.progress, coalesce(left(j.error,200),'') from jobs j where j.project_id = '$1' and j.kind = 'comic' order by j.created_at desc limit 1")"
  if [ -n "$row" ] && [ "$row" != "$last" ]; then echo "$(date +%H:%M:%S) $row"; last="$row"; fi
  case "$row" in done*|failed*) echo "FINISHED"; exit 0 ;; esac
  sleep 20
done
