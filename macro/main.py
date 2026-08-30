"""Run the Midi Fighter 3D macro controller.

Reads a TOML config, opens the device for input, and dispatches pad/tilt/bank/
side events to actions. Works today — input needs no LED unblock. Bank buttons
1-4 switch layers.

Examples:
    # Live control (default config), executing real actions:
    python -m macro.main

    # Safe preview — prints what WOULD run without touching Sway/keys:
    python -m macro.main --dry-run

    # Custom config:
    python -m macro.main --config ~/my-macros.toml
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from midifighter.device import MidiFighter3D
from midifighter.ports import DeviceNotFoundError
from midifighter.sinks import DeviceSink

from .config import load_config
from .engine import MacroController
from .leds import LayerLeds

_DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "config.toml")


def main(argv=None) -> int:
    """Run the controller loop. Returns exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=_DEFAULT_CONFIG,
                        help="path to a TOML config (default: macro/config.toml)")
    parser.add_argument("--dry-run", action="store_true",
                        help="preview actions without executing them")
    parser.add_argument("--tilt-high", type=int, default=None,
                        help="tilt activation threshold 1-127 (lower = lighter "
                             "tilt; overrides config)")
    parser.add_argument("--tilt-low", type=int, default=None,
                        help="tilt re-arm threshold (overrides config)")
    parser.add_argument("--no-leds", action="store_true",
                        help="disable LED feedback on the grid")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except (OSError, ValueError) as exc:
        print(f"[FAIL] config: {exc}")
        return 1

    controller = MacroController(config, dry_run=args.dry_run,
                                 on_fire=lambda s: print(s, flush=True),
                                 tilt_high=args.tilt_high, tilt_low=args.tilt_low)

    try:
        device = MidiFighter3D(on_event=controller.handle).open()
    except DeviceNotFoundError as exc:
        print(f"[FAIL] {exc}")
        return 1

    leds = None
    if not args.no_leds:
        leds = LayerLeds(DeviceSink(device))
        controller.leds = leds
        controller.start_leds()          # paint initial layer now that device is open

    mode = "DRY-RUN (no real actions)" if args.dry_run else "LIVE"
    print(f"Macro controller running [{mode}]. Start layer: {config.start}")
    print(f"Layers by bank button: {', '.join(f'{i+1}={n}' for i, n in enumerate(config.banks))}")
    print(f"Tilt threshold: high={controller.tilt_high} low={controller.tilt_low}")
    print(f"LED feedback: {'off' if leds is None else 'on (mapped pads glow, press=flash)'}")
    print("Press pads / tilt / bank buttons. Ctrl-C to quit.\n")
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[exit]")
    finally:
        if leds is not None:
            leds.clear()
        device.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
