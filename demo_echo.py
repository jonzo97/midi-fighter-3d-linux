#!/usr/bin/env python3
"""Phase 2 demo — press a pad, it lights up; release, it clears.

The simplest end-to-end proof of the driver: input events drive LED output in
real time. Bright color while held, off on release. Ctrl-C to exit (clears grid).

Requires that PAD_NOTES is correct — run tools/capture_input.py first if pads
don't light the ring you pressed.

Run:
    . .venv/bin/activate && python demo_echo.py
"""

from __future__ import annotations

import sys
import time

from midifighter.device import ButtonDown, ButtonUp, MidiFighter3D
from midifighter.ports import DeviceNotFoundError
from midifighter import protocol as p

# Cycle a color per press so consecutive hits are visually distinct.
_HUES = p.HUE_ORDER


def main() -> int:
    """Run the echo demo. Returns exit code."""
    state = {"n": 0}

    def handle(ev) -> None:
        if isinstance(ev, ButtonDown):
            color = _HUES[state["n"] % len(_HUES)]
            state["n"] += 1
            mf.set_color(ev.pad, color, bright=True)
            print(f"  pad {ev.pad:2d} down -> {color}")
        elif isinstance(ev, ButtonUp):
            mf.clear(ev.pad)
            print(f"  pad {ev.pad:2d} up")

    try:
        mf = MidiFighter3D(on_event=handle).open()
    except DeviceNotFoundError as exc:
        print(f"[FAIL] {exc}")
        return 1

    print("Echo demo live. Press pads (Ctrl-C to quit).")
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[exit] clearing grid")
    finally:
        mf.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
