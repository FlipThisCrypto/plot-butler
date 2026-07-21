# The Plot Butler

Operations console and transfer scheduler for Gigahorse C7 plotting on this host, with remote plot delivery to **chiamain** and a reserved GPU for **chia_recompute_server**.

## What it does

- Dashboard on port **8088** (plot pipeline, GPUs, temps, drives, transfers)
- Spools finished plots off NVMe and rsyncs them to remote harvester mounts
- **Recompute-aware transfer policy**: single stream, 12 MiB/s cap, pauses shipping when recompute latency enters stale-share range

## Services

| Unit | Role |
|------|------|
| `plot-butler.service` | Dashboard + transfer scheduler |
| `gigahorse-plotter.service` | Plot loop (GPU 0) |
| `chia-recompute.service` | Farming recompute (GPU 1, port 11989) |

## Transfer / recompute policy

Plot rsync and recompute share the Tailscale path to chiamain. Farming wins:

- `MAX_ACTIVE_TRANSFERS=1`
- `RSYNC_BWLIMIT_KBPS=12000` (~12 MiB/s)
- Pause new transfers when recent recompute p90 ≥ 5 s or max ≥ 20 s
- Resume when p90 ≤ 2.5 s (hysteresis)

Live metrics: `/api/state` → `recompute`, `transfer_policy`, `alerts`.
