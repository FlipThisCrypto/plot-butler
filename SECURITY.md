# Security Policy

## Reporting

Open a private security advisory on GitHub or contact the maintainers via the repository.

## Hardening checklist

- Set `PLOT_BUTLER_API_TOKEN` for POST control endpoints.
- Bind with `PLOT_BUTLER_BIND=127.0.0.1` if only local access is needed (or front with reverse proxy + TLS).
- Keep `plotter.env` and `plot-butler.env` out of git (see `.gitignore`).
- Prefer SSH keys with limited farmer accounts for rsync/`chia plots add`.
- Do not commit farmer private keys or mnemonics (public farmer keys in plotter.env are still farm-identifying).

## Known trust boundaries

- Dashboard HTTP is unauthenticated for GET by default.
- SSH to the farmer runs with the service user credentials.
- `systemctl start` for plotter/recompute requires passwordless sudo where enabled.
