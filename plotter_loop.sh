#!/usr/bin/env bash
# Gigahorse plot loop. Secrets/paths come from plotter.env (not committed).
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
if [[ -f "$ROOT/plotter.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/plotter.env"
  set +a
fi

PLOTTER="${PLOTTER:-/home/smokey/gigahorse/cuda_plot_k32}"
PLOT_STAGING="${PLOT_STAGING:-/home/smokey/plots/staging}"
PLOT_TEMP="${PLOT_TEMP:-/home/smokey/plots/temp}"
PLOT_DEST="${PLOT_DEST:-/home/smokey/plots/staging}"
PLOT_COMPRESSION="${PLOT_COMPRESSION:-7}"
PLOT_GPU="${PLOT_GPU:-0}"
LOG="${PLOT_LOG:-/home/smokey/logs/gigahorse-c7-live.log}"

if [[ -z "${PLOT_CONTRACT:-}" || -z "${PLOT_FARMER_PK:-}" ]]; then
  echo "plotter_loop: PLOT_CONTRACT and PLOT_FARMER_PK must be set (see plotter.env.example)" >&2
  sleep 60
  exit 1
fi

mkdir -p "$(dirname "$LOG")" "$PLOT_STAGING" "$PLOT_TEMP" "$PLOT_DEST"

while true; do
  if "$ROOT/plot_capacity_guard.sh"; then
    "$PLOTTER" -n 1 -C "$PLOT_COMPRESSION" -g "$PLOT_GPU" \
      -t "$PLOT_STAGING/" \
      -3 "$PLOT_TEMP/" \
      -d "$PLOT_DEST/" \
      -c "$PLOT_CONTRACT" \
      -f "$PLOT_FARMER_PK" \
      -Q 1 -D 2>&1 | tee -a "$LOG"
    rc=${PIPESTATUS[0]}
    [[ "$rc" -eq 0 ]] || sleep 30
  else
    sleep 300
  fi
done
