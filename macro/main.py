"""Run the Midi Fighter 3D macro controller.

Reads a TOML config, opens the device for input, and dispatches pad/tilt/bank/
side events to actions. Works today — input needs no LED unblock. Bank buttons
1-4 switch layers. With ``[auto]`` in the config it also follows sway: the
review bank on the review desks, and silence while the Tower page is focused
(macro/desks.py).

Examples:
    # Live control (default config), executing real actions:
    python -m macro.main

    # Safe preview — prints what WOULD run without touching Sway/keys:
    python -m macro.main --dry-run

    # As a service: wait for the device, survive unplug/replug:
    python -m macro.main --wait-device

    # Custom config:
    python -m macro.main --config ~/my-macros.toml
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from typing import Callable

from midifighter.device import MidiFighter3D
from midifighter.ports import DeviceNotFoundError, find_input_name
from midifighter.sinks import DeviceSink

from .config import load_config
from .desks import DeskFollower, SwayWatcher
from .engine import MacroController
from .leds import LayerLeds

_DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "config.toml")
# Seconds between checks that the device is (still) plugged in.
DEVICE_POLL_S = 3.0


def _log(line: str) -> None:
    print(line, flush=True)


def _device_present() -> bool:
    try:
        find_input_name()
        return True
    except DeviceNotFoundError:
        return False
    except Exception:  # noqa: BLE001 - a MIDI backend hiccup is "not present"
        return False


def _connect(controller: MacroController, use_leds: bool):
    """Open the device and hook up LED feedback.

    Returns:
        tuple: (device, leds-or-None).

    Raises:
        DeviceNotFoundError: If the device is not plugged in.
    """
    device = MidiFighter3D(on_event=controller.handle).open(output=use_leds)
    leds = None
    if use_leds:
        leds = LayerLeds(DeviceSink(device))
        controller.leds = leds
        controller.start_leds()      # paint the active layer now the device is open
    return device, leds


def _disconnect(controller: MacroController, device, leds, gone: bool) -> None:
    """Close the device; skip LED writes when it is already unplugged."""
    controller.leds = None
    try:
        if leds is not None and not gone:
            leds.clear()
    except Exception:  # noqa: BLE001 - closing must not raise
        pass
    try:
        if gone:
            device._out = None       # nothing to clear on a vanished port
        device.close()
    except Exception:  # noqa: BLE001
        pass


def run_device_loop(connect: Callable[[], tuple],
                    disconnect: Callable[[object, object, bool], None],
                    present: Callable[[], bool], wait: bool,
                    stop: threading.Event, poll: float = DEVICE_POLL_S,
                    log: Callable[[str], None] = _log) -> int:
    """Keep the device connected until ``stop`` is set.

    Args:
        connect: Opens the device; returns (device, leds) or raises
            DeviceNotFoundError.
        disconnect: Closes (device, leds, gone) where gone means unplugged.
        present: True while the device's port exists.
        wait: Wait for a missing device (and reconnect after an unplug)
            instead of returning 1.
        stop: Set to end the loop (Ctrl-C, SIGTERM).
        poll: Seconds between presence checks.
        log: Callable(str) for status lines.

    Returns:
        int: 0 after a requested stop, 1 if the device is missing and not waiting.
    """
    device = leds = None
    waiting_said = False
    try:
        while not stop.is_set():
            if device is None:
                try:
                    device, leds = connect()
                except DeviceNotFoundError as exc:
                    if not wait:
                        print(f"[FAIL] {exc}", flush=True)
                        return 1
                    if not waiting_said:
                        log("[device] not plugged in; waiting")
                        waiting_said = True
                    stop.wait(poll)
                    continue
                log("[device] connected")
                waiting_said = False
            stop.wait(poll)
            if not stop.is_set() and not present():
                log("[device] unplugged")
                disconnect(device, leds, True)
                device = leds = None
                if not wait:
                    return 1
        return 0
    finally:
        if device is not None:
            disconnect(device, leds, False)


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
                        help="disable LED feedback (opens the input port only)")
    parser.add_argument("--no-follow", action="store_true",
                        help="ignore the [auto] sway desk follower")
    parser.add_argument("--wait-device", action="store_true",
                        help="wait for the device instead of exiting, and "
                             "reconnect after an unplug")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except (OSError, ValueError) as exc:
        print(f"[FAIL] config: {exc}")
        return 1

    controller = MacroController(config, dry_run=args.dry_run, on_fire=_log,
                                 tilt_high=args.tilt_high, tilt_low=args.tilt_low)
    stop = threading.Event()
    # systemd stops us with SIGTERM: unwind through the finally below.
    signal.signal(signal.SIGTERM, lambda *_a: stop.set())

    mode = "DRY-RUN (no real actions)" if args.dry_run else "LIVE"
    print(f"Macro controller running [{mode}]. Start layer: {config.start}")
    print(f"Layers by bank button: {', '.join(f'{i+1}={n}' for i, n in enumerate(config.banks))}")
    print(f"Tilt threshold: high={controller.tilt_high} low={controller.tilt_low}")
    print(f"LED feedback: {'off' if args.no_leds else 'on (mapped pads glow, press=flash)'}")

    watcher = None
    if config.auto.enabled and not args.no_follow:
        follower = DeskFollower(controller, config.auto, log=_log)
        watcher = SwayWatcher(follower, log=_log).start()
        desks = ", ".join(str(n) for n in config.auto.review_workspaces)
        print(f"Desk follow: on (review bank on workspace {desks}; Tower mute)")
    print("Press pads / tilt / bank buttons. Ctrl-C to quit.\n", flush=True)

    try:
        return run_device_loop(
            lambda: _connect(controller, not args.no_leds),
            lambda device, leds, gone: _disconnect(controller, device, leds, gone),
            _device_present, wait=args.wait_device, stop=stop)
    except KeyboardInterrupt:
        return 0
    finally:
        print("\n[exit]", flush=True)
        if watcher is not None:
            watcher.stop()


if __name__ == "__main__":
    sys.exit(main())
