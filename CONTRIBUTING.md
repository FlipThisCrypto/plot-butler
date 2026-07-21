# Contributing

## Development

```bash
python3 -m unittest discover -s tests -v
bash -n plotter_loop.sh plot_capacity_guard.sh
```

## Guidelines

- Prefer farming safety over transfer throughput.
- Do not commit `plotter.env`, `plot-butler.env`, or real farm keys.
- Keep iterations focused; add tests for gate/parser changes.
- Match existing Python style (compact, stdlib-only).

## Pull requests

CI must pass. Describe farming impact (latency, bandwidth, disk).
