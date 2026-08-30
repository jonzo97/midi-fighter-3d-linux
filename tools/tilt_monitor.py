#!/usr/bin/env python3
"""Live tilt monitor — find your comfortable tilt threshold.

Prints each edge's current CC value and the running MAX you've reached, so you
can pick a `tilt_high` for macro/config.toml. Tilt each edge as far as feels
natural; use the peak values (minus a little headroom) as your threshold.

Run:
    . .venv/bin/activate && python tools/tilt_monitor.py
"""

from __future__ import annotations

import os
import sys
import time

import mido

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from midifighter import protocol as p  # noqa: E402
from midifighter.ports import DeviceNotFoundError, find_input_name  # noqa: E402

_EDGE = {p.TILT_LEFT_CC: "left", p.TILT_FORWARD_CC: "forward",
         p.TILT_RIGHT_CC: "right", p.TILT_BACK_CC: "back"}
MOTION_CH0 = p.to_mido(p.MOTION_CHANNEL)


def main() -> int:
    """Run the tilt monitor. Returns exit code."""
    try:
        in_name = find_input_name()
    except DeviceNotFoundError as exc:
        print(f"[FAIL] {exc}")
        return 1

    cur = {"left": 0, "forward": 0, "right": 0, "back": 0}
    peak = dict(cur)
    print(f"[ok] {in_name} — tilt each edge; Ctrl-C when done.\n")
    try:
        with mido.open_input(in_name) as port:
            while True:
                for msg in port.iter_pending():
                    if msg.type == "control_change" and msg.channel == MOTION_CH0:
                        edge = _EDGE.get(msg.control)
                        if edge:
                            cur[edge] = msg.value
                            peak[edge] = max(peak[edge], msg.value)
                row = "  ".join(f"{e}:{cur[e]:3d}(max{peak[e]:3d})" for e in cur)
                sys.stdout.write("\r" + row)
                sys.stdout.flush()
                time.sleep(0.02)
    except KeyboardInterrupt:
        print("\n\n=== peak values ===")
        for e in cur:
            print(f"  {e:8s} peak {peak[e]}")
        lo = min(peak.values())
        print(f"\nSuggested tilt_high ~= {max(20, int(lo * 0.7))} "
              f"(70% of your lightest edge's peak).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
