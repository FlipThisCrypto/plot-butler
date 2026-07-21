#!/usr/bin/env bash
set -u
PLOTTER=/home/smokey/gigahorse/cuda_plot_k32
while true; do
  if /home/smokey/plot-butler/plot_capacity_guard.sh; then
    "$PLOTTER" -n 1 -C 7 -g 0 \
      -t /home/smokey/plots/staging/ \
      -3 /home/smokey/plots/temp/ \
      -d /home/smokey/plots/staging/ \
      -c xch10e9e0xddh2wv4y4d4al57p0ere5q5mq0xhzfpxvtrsakkncqn4xsga9nmy \
      -f 933ec1c0da9b6d763c245e5d1e98dabbe0493540ffdd0c7ba4bc01551035a95bdc8f3306435c2e4431a1175af12468a3 \
      -Q 1 -D 2>&1 | tee -a /home/smokey/logs/gigahorse-c7-live.log
    rc=${PIPESTATUS[0]}
    [[ "$rc" -eq 0 ]] || sleep 30
  else
    sleep 300
  fi
done

