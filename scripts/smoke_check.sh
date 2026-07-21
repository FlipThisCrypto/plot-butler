#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
base="${1:-http://127.0.0.1:8088}"
echo "health:" "$(curl -fsS "$base/api/health" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("ok"),d.get("recompute_health"),d.get("harvester_health"), "staging", d.get("staging_free_gb"))')"
echo "metrics lines:" "$(curl -fsS "$base/api/metrics" | wc -l)"
python3 -m unittest discover -s "$ROOT/tests" -q
echo "smoke ok"
