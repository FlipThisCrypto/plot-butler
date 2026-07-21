#!/usr/bin/env bash
set -euo pipefail
for u in plot-butler.service chia-recompute.service; do
  echo -n "$u: "
  systemctl is-active "$u" || true
done
systemctl cat plot-butler.service | grep -E 'EnvironmentFile|ExecStart|Nice' || true
