"""Runnable LED animation showcase.

Renders animations to the terminal simulator (works today) or the real device
(after 4-Banks Mode is disabled). If input is enabled and the device is present,
real pad presses drive the reactive/ripple animations live — input already works
regardless of the LED block.

Examples:
    # Terminal simulator, live pad input, cycle all animations:
    python -m midifighter.showcase

    # Real hardware LEDs (needs banks mode disabled):
    python -m midifighter.showcase --sink device

    # One animation, no input:
    python -m midifighter.showcase --anim rainbow --input off --seconds 15
"""

from __future__ import annotations

import argparse
import sys

from .animations import Engine, RainbowSweep, Reactive, Ripple
from .device import MidiFighter3D
from .ports import DeviceNotFoundError
from .sinks import DeviceSink, TerminalSink

ANIMS = {
    "reactive": Reactive,
    "rainbow": RainbowSweep,
    "ripple": Ripple,
}


def main(argv=None) -> int:
    """Run the showcase. Returns exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sink", choices=["terminal", "device"],
                        default="terminal", help="where LEDs render")
    parser.add_argument("--input", choices=["on", "off"], default="on",
                        help="read live pad input (default on)")
    parser.add_argument("--anim", choices=[*ANIMS, "all"], default="all")
    parser.add_argument("--seconds", type=float, default=12.0,
                        help="seconds per animation (default 12)")
    args = parser.parse_args(argv)

    device = None
    if args.input == "on" or args.sink == "device":
        try:
            device = MidiFighter3D().open()
        except DeviceNotFoundError as exc:
            if args.sink == "device":
                print(f"[FAIL] {exc}")
                return 1
            print(f"[warn] no device for input ({exc}); running without input")

    sink = DeviceSink(device) if args.sink == "device" else TerminalSink()
    engine = Engine(sink, device=device)

    selected = list(ANIMS) if args.anim == "all" else [args.anim]
    try:
        for key in selected:
            anim = ANIMS[key]()
            if args.sink == "terminal":
                sys.stdout.write("\x1b[2J\x1b[H")
                print(f"  >>> {anim.name}  "
                      f"({'press pads! ' if device else ''}Ctrl-C to skip)\n")
            engine.run(anim, args.seconds)
    except KeyboardInterrupt:
        print("\n[exit]")
    finally:
        if device is not None:
            device.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
