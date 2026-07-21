# The Plot Butler

Operations console and transfer scheduler for Gigahorse C7 plotting on this host,
with remote plot delivery to **chiamain** and a reserved GPU for **chia_recompute_server**.

## Critical design rule

Plot rsync and farming recompute share the Tailscale path to chiamain.
**Farming wins.** Transfers throttle and pause when recompute or harvester
quality latency enters stale-share range.

## Services

| Unit | Role |
|------|------|
| `plot-butler.service` | Dashboard + transfer scheduler + temp cleanup |
| `gigahorse-plotter.service` | Plot loop (GPU 0) |
| `chia-recompute.service` | Farming recompute (GPU 1, port 11989) |

Install/update units and priority drop-ins:

```bash
./install-systemd.sh
sudo systemctl restart chia-recompute.service plot-butler.service
```

## Transfer / recompute policy

| Knob | Default | Env override |
|------|---------|----------------|
| Max concurrent rsync | 1 | `PLOT_BUTLER_MAX_TRANSFERS` |
| Bandwidth cap | 12 MiB/s | `PLOT_BUTLER_BWLIMIT_KBPS` |
| Warm start after pause | 6 MiB/s | `PLOT_BUTLER_BWLIMIT_WARM_KBPS` |
| Pause on recompute p90 | 5000 ms | `PLOT_BUTLER_RECOMPUTE_PAUSE_P90_MS` |
| Pause on harvester max | 15 s | `PLOT_BUTLER_HARVESTER_PAUSE_S` |

Other:

- Prefer destinations away from the mount of the worst recent quality lookup
- SIGTERM in-flight rsync when farming gate trips (`--partial` resumes later)
- Orphan `cuda_plot_tmp*` cleanup every 5 minutes
- Optional `PLOT_BUTLER_API_TOKEN` for POST controls

## HTTP API

| Path | Description |
|------|-------------|
| `GET /` | Dashboard |
| `GET /api/state` | Full telemetry JSON |
| `GET /api/health` | Compact health (200 / 503) |
| `GET /api/metrics` | Prometheus text metrics |
| `POST /api/pause-transfers` | Manual pause |
| `POST /api/resume-transfers` | Manual resume |
| `POST /api/start-plotting` | Start plotter unit |
| `POST /api/start-recompute` | Start recompute unit |

## Tests

```bash
python3 -m unittest tests.test_farming_gate -v
```

## Logs

- `plot-butler-events.log` — JSON events (pause/resume/transfer/cleanup)
- `journalctl -u plot-butler.service`
- `journalctl -u chia-recompute.service`
