#!/usr/bin/env bash
# Install Plot Butler units and farming-priority drop-ins.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
sudo install -d /etc/systemd/system/chia-recompute.service.d
sudo install -d /etc/systemd/system/plot-butler.service.d
sudo install -m 644 "$ROOT/plot-butler.service" /etc/systemd/system/plot-butler.service
sudo install -m 644 "$ROOT/gigahorse-plotter.service" /etc/systemd/system/gigahorse-plotter.service
sudo install -m 644 "$ROOT/systemd/chia-recompute.service.d/priority.conf" \
  /etc/systemd/system/chia-recompute.service.d/priority.conf
sudo install -m 644 "$ROOT/systemd/plot-butler.service.d/priority.conf" \
  /etc/systemd/system/plot-butler.service.d/priority.conf
sudo systemctl daemon-reload
sudo systemctl enable plot-butler.service
echo "Installed. Restart when ready:"
echo "  sudo systemctl restart chia-recompute.service plot-butler.service"
