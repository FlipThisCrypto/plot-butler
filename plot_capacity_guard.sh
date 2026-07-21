#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
[[ -f "$ROOT/plotter.env" ]] && set -a && source "$ROOT/plotter.env" && set +a
[[ -f "$ROOT/plot-butler.env" ]] && set -a && source "$ROOT/plot-butler.env" && set +a

MIN_KB=94371840  # 90 GiB remote
SPOOL="${PLOT_BUTLER_SPOOL:-/media/smokey/1002/plot-butler/staging}"
STAGING="${PLOT_BUTLER_STAGING:-/home/smokey/plots/staging}"
# Leave room for one plot + temp headroom on local paths
LOCAL_MIN_KB=$((120 * 1024 * 1024))  # 120 GiB

if [[ -d "$SPOOL" ]]; then
  free_spool=$(df -P "$SPOOL" | awk 'NR==2{print $4}')
  if [[ "${free_spool:-0}" -lt "$LOCAL_MIN_KB" ]]; then
    echo "Local spool $SPOOL has under 120 GiB free (${free_spool:-0} KB); plotting paused." >&2
    exit 75
  fi
fi
if [[ -d "$STAGING" ]]; then
  free_stg=$(df -P "$STAGING" | awk 'NR==2{print $4}')
  if [[ "${free_stg:-0}" -lt "$LOCAL_MIN_KB" ]]; then
    echo "Local staging $STAGING has under 120 GiB free (${free_stg:-0} KB); plotting paused." >&2
    exit 75
  fi
fi

REMOTE="${PLOT_BUTLER_REMOTE:-chiamain@100.101.40.76}"
eligible=$(
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$REMOTE" '
    df -P -T -x tmpfs -x devtmpfs -x squashfs 2>/dev/null |
    awk "NR>1 && \$1 != \"/dev/sda2\" && \$7 ~ /^\/media\// && \$2 != \"vfat\" && \$5 > '"$MIN_KB"' {print \$7}"
  ' || true
)
if [[ -n "$eligible" ]]; then
  exit 0
fi
echo "No remote filesystem has at least 90 GiB free; plotting paused." >&2
exit 75
