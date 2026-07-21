# Deploy snippets

- `prometheus-plot-butler.yml` — scrape Plot Butler metrics
- Prefer systemd units from repo root via `../install-systemd.sh`
- For reverse proxy: TLS terminate and set `PLOT_BUTLER_BIND=127.0.0.1`
