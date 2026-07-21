# Changelog

## 1.61.0

- Smoke check accepts degraded (503) health responses
- Critical alert if recompute unit inactive
- Spool free-space drain pause; transfer failure cooldown
- Open-source packaging (CI, SECURITY, CONTRIBUTING, Docker)

## 1.58.0

- Active vs orphan plot temp accounting and alerts
- Faster reclaim of large orphan cuda_plot_tmp files
- plotter.env for secrets; env-configurable paths/remote
- Prefer native Linux FS destinations over NTFS
- Local capacity guard for staging/spool
- Failed transfer cooldown; POST rate limit
- GitHub Actions CI; SECURITY/CONTRIBUTING docs

## 1.50.0

- Farming-first transfer gating (recompute + harvester latency)
- Dashboard, metrics, health endpoints
- systemd priority drop-ins for recompute
