#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
base="${1:-http://127.0.0.1:8088}"
ok=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  code=$(curl -sS --max-time 3 -o /tmp/pb-health.json -w '%{http_code}' "$base/api/health" || echo 000)
  if [[ "$code" == "200" || "$code" == "503" ]] && python3 -c 'import json;json.load(open("/tmp/pb-health.json"))' 2>/dev/null; then
    echo "health HTTP $code: $(python3 -c 'import json;d=json.load(open("/tmp/pb-health.json"));print(d.get("ok"),d.get("recompute_health"),d.get("harvester_health"),"staging",d.get("staging_free_gb"))')"
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "health: unavailable after retries" >&2
  exit 1
fi
echo "metrics lines: $(curl -fsS --max-time 3 "$base/api/metrics" | wc -l)"
python3 -m unittest discover -s "$ROOT/tests" -q
echo "smoke ok"
