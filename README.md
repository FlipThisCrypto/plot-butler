# The Plot Butler

[![CI](https://github.com/FlipThisCrypto/plot-butler/actions/workflows/ci.yml/badge.svg)](https://github.com/FlipThisCrypto/plot-butler/actions/workflows/ci.yml)

**Open source:** [github.com/FlipThisCrypto/plot-butler](https://github.com/FlipThisCrypto/plot-butler)

Operations console and transfer scheduler for **Gigahorse** Chia plotting with a reserved GPU for **`chia_recompute_server`**. Plot rsync shares the network path with farming recompute — **farming wins**.

## Why it exists

Bulk plot shipping can starve recompute / harvester latency and cause **stale shares**. Plot Butler:

- Caps and serializes plot transfers
- Pauses shipping when recompute or harvester quality latency is dangerous
- Surfaces farming health on a local dashboard and Prometheus metrics
- Cleans orphan Gigahorse temp files before they fill the plot NVMe

## Quick start

```bash
git clone https://github.com/FlipThisCrypto/plot-butler.git
cd plot-butler
# Edit paths/REMOTE/plotter args in plot_butler.py, plotter_loop.sh, and unit files for your hosts
./install-systemd.sh
sudo systemctl restart chia-recompute.service plot-butler.service
```

Dashboard default: `http://<host>:8088`

```bash
make test
./scripts/smoke_check.sh
make health
```

## Critical design rule

Plot rsync and farming recompute often share the same path to the farmer (e.g. Tailscale).

**Farming wins.** Transfers throttle and pause when recompute or harvester quality latency enters stale-share range.

## Services

| Unit | Role |
|------|------|
| `plot-butler.service` | Dashboard + transfer scheduler + temp cleanup |
| `gigahorse-plotter.service` | Plot loop (typically GPU 0) |
| `chia-recompute.service` | Farming recompute (typically GPU 1, port 11989) |

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
- Optional `PLOT_BUTLER_BIND` (default `0.0.0.0`)

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

## Configuration

This repository ships with paths and hostnames for a reference deployment. Before production use, set:

- Staging / spool / temp directories in `plot_butler.py`
- SSH remote farmer host (`REMOTE`)
- Plotter binary and keys in `plotter.env` (copy from `plotter.env.example`; never commit secrets)
- Systemd unit user and working directories

## Tests

```bash
python3 -m unittest discover -s tests -v
# or
make test
```

## Logs

- `plot-butler-events.log` — JSON events (pause/resume/transfer/cleanup)
- `journalctl -u plot-butler.service`
- `journalctl -u chia-recompute.service`

## Log rotation

```bash
sudo cp logrotate-plot-butler.conf /etc/logrotate.d/plot-butler
```

## Stale share recovery

1. Check `GET /api/health` and dashboard recompute/harvester latency.
2. If degraded: transfers auto-pause; confirm with `POST /api/pause-transfers`.
3. Watch `journalctl -u chia-recompute.service -f` for request times (want << 5s).
4. On farmer: quality lookups in the harvester debug log should be << 20s.
5. Free NVMe if staging full: plot-butler cleans orphan `cuda_plot_tmp*`; verify `df -h /`.
6. When healthy: `POST /api/resume-transfers` (warm bandwidth applies for 30m).

## Version

See `VERSION` in `plot_butler.py` and [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).
