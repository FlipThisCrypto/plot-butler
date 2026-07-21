#!/usr/bin/env bash
set -euo pipefail
MIN_KB=94371840
eligible=$(
  ssh -o BatchMode=yes -o ConnectTimeout=5 chiamain@100.101.40.76 '
    df -P -T -x tmpfs -x devtmpfs -x squashfs 2>/dev/null |
    awk "NR>1 && \$1 != \"/dev/sda2\" && \$7 ~ /^\\/media\\/chiamain\\// && \$2 != \"vfat\" && \$5 > '"$MIN_KB"' {print \$7}"
  ' || true
)
if [[ -n "$eligible" ]]; then
  exit 0
fi
echo "No non-OS chiamain filesystem has at least 90 GiB free; plotting paused." >&2
exit 75
