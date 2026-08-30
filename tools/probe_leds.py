#!/usr/bin/env python3
"""Phase 1 LED prober — nail down the color channel, animation channel, banks.

LEDs are driven by sending Note-On messages whose note matches a pad's note and
whose velocity selects a palette color (base channel) or an animation (base+1).
Because the true pad notes and the effect of 4-Banks Mode can only be confirmed
by watching the hardware, this tool drives well-defined sweeps the user watches.

Modes:
    off     clear the whole candidate note range (velocity 0)
    sweep   light each note in the range one at a time (reveals pad<->note map)
    colors  cycle the full 10-color x bright/dim palette on one note
    anim    cycle brightness/gate/pulse animations on one note (base+1 channel)

Run in the project venv, e.g.:
    . .venv/bin/activate && python tools/probe_leds.py --mode sweep
    . .venv/bin/activate && python tools/probe_leds.py --mode colors --note 60
    . .venv/bin/activate && python tools/probe_leds.py --mode off
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import mido

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from midifighter.ports import DeviceNotFoundError, find_output_name  # noqa: E402

# Color name -> (bright velocity, dim velocity), from user guide Fig 2.
COLOR_TABLE = {
    "red": (13, 19), "orange": (25, 31), "yellow": (37, 43),
    "lime": (49, 55), "green": (61, 67), "cyan": (73, 79),
    "blue": (85, 91), "purple": (97, 103), "magenta": (109, 115),
    "white": (121, 5),
}
# Animation velocity bands (sent on base+1 channel), from user guide.
ANIM_SAMPLES = {
    "bright-25%": 22, "bright-50%": 26, "bright-100%": 33,
    "gate-1/4": 36, "gate-1/2": 39, "pulse-1/4": 44, "pulse-1/2": 47,
}


def send_color(port, ch0: int, note: int, velocity: int) -> None:
    """Send one color/animation Note-On (ch0 is 0-indexed mido channel)."""
    port.send(mido.Message("note_on", channel=ch0, note=note, velocity=velocity))


def mode_off(port, ch0: int, lo: int, hi: int) -> None:
    """Clear every note in [lo, hi] on both base and base+1 channels."""
    for note in range(lo, hi + 1):
        send_color(port, ch0, note, 0)
        send_color(port, ch0 + 1, note, 0)
    print(f"[ok] cleared notes {lo}-{hi} on ch{ch0 + 1}/{ch0 + 2}")


def mode_sweep(port, ch0: int, lo: int, hi: int, dwell: float) -> None:
    """Light one note at a time so the user can map note number -> physical pad."""
    print(f"[watch] sweeping notes {lo}-{hi} on ch{ch0 + 1}, {dwell}s each")
    for note in range(lo, hi + 1):
        send_color(port, ch0, note, COLOR_TABLE["red"][0])
        print(f"  note {note} -> bright red")
        time.sleep(dwell)
        send_color(port, ch0, note, 0)


def mode_colors(port, ch0: int, note: int, dwell: float) -> None:
    """Cycle the whole palette on a single note to confirm the color channel."""
    print(f"[watch] cycling palette on note {note}, ch{ch0 + 1}")
    for name, (bright, dim) in COLOR_TABLE.items():
        send_color(port, ch0, note, bright)
        print(f"  {name} bright (vel {bright})")
        time.sleep(dwell)
        send_color(port, ch0, note, dim)
        print(f"  {name} dim (vel {dim})")
        time.sleep(dwell)
    send_color(port, ch0, note, 0)


def mode_anim(port, ch0: int, note: int, dwell: float) -> None:
    """Set a base color then cycle animations on the base+1 channel."""
    print(f"[watch] animations on note {note}: color ch{ch0 + 1}, anim ch{ch0 + 2}")
    send_color(port, ch0, note, COLOR_TABLE["red"][0])  # base color first
    for name, vel in ANIM_SAMPLES.items():
        send_color(port, ch0 + 1, note, vel)
        print(f"  {name} (anim vel {vel})")
        time.sleep(dwell)
    send_color(port, ch0 + 1, note, 0)
    send_color(port, ch0, note, 0)


def main() -> int:
    """Drive the selected LED probe. Returns exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["off", "sweep", "colors", "anim"],
                        default="sweep")
    parser.add_argument("--channel", type=int, default=3,
                        help="base MIDI channel, 1-indexed (default 3)")
    parser.add_argument("--note", type=int, default=36,
                        help="note for colors/anim modes; must be a real pad "
                             "(VERIFIED pads = notes 36..51) (default 36)")
    parser.add_argument("--note-min", type=int, default=36)
    parser.add_argument("--note-max", type=int, default=51)  # VERIFIED pad range
    parser.add_argument("--dwell", type=float, default=0.4,
                        help="seconds per step (default 0.4)")
    args = parser.parse_args()
    ch0 = args.channel - 1  # to mido 0-indexed

    try:
        out_name = find_output_name()
    except DeviceNotFoundError as exc:
        print(f"[FAIL] {exc}")
        return 1

    print(f"[ok] output: {out_name}")
    with mido.open_output(out_name) as port:
        if args.mode == "off":
            mode_off(port, ch0, args.note_min, args.note_max)
        elif args.mode == "sweep":
            mode_sweep(port, ch0, args.note_min, args.note_max, args.dwell)
        elif args.mode == "colors":
            mode_colors(port, ch0, args.note, args.dwell)
        elif args.mode == "anim":
            mode_anim(port, ch0, args.note, args.dwell)
        # Always leave the grid clean.
        mode_off(port, ch0, args.note_min, args.note_max)
    return 0


if __name__ == "__main__":
    sys.exit(main())
