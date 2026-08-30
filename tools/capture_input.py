#!/usr/bin/env python3
"""Phase 1 input capture — reveal the real pad-note map and channels.

Passive logger: opens the Midi Fighter 3D input port and decodes every message
as it arrives. Press all 16 arcade pads (any order), the 4 bank buttons, the 6
side buttons, then tilt/rotate the device. On exit (Ctrl-C or timeout) it prints
a tally of every unique event seen and writes it to tools/capture_log.json, so
the exact note number of each pad and the exact channel bytes are captured as
measured truth rather than guessed from the 0-indexed user guide.

Run in the project venv:
    . .venv/bin/activate && python tools/capture_input.py            # runs 60s
    . .venv/bin/activate && python tools/capture_input.py --seconds 0  # until Ctrl-C
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter

import mido

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from midifighter.ports import DeviceNotFoundError, find_input_name  # noqa: E402

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capture_log.json")


def _key(msg: mido.Message) -> str:
    """Stable identity for an event kind (ignoring velocity/value)."""
    if msg.type in ("note_on", "note_off"):
        # MIDI channel shown 1-indexed for human readability.
        return f"{msg.type} ch{msg.channel + 1} note{msg.note}"
    if msg.type == "control_change":
        return f"control_change ch{msg.channel + 1} cc{msg.control}"
    return f"{msg.type} ch{getattr(msg, 'channel', -1) + 1}"


def main() -> int:
    """Capture and summarise Midi Fighter 3D input. Returns exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seconds", type=float, default=60.0,
        help="capture duration; 0 = until Ctrl-C (default 60)",
    )
    args = parser.parse_args()

    try:
        in_name = find_input_name()
    except DeviceNotFoundError as exc:
        print(f"[FAIL] {exc}")
        return 1

    print(f"[ok] listening on: {in_name}")
    print("     Press ALL 16 pads, the 4 bank + 6 side buttons, then tilt/rotate.")
    print("     Ctrl-C when done.\n")

    seen: Counter[str] = Counter()
    events: list[dict] = []
    deadline = None if args.seconds == 0 else time.monotonic() + args.seconds

    try:
        with mido.open_input(in_name) as port:
            while deadline is None or time.monotonic() < deadline:
                for msg in port.iter_pending():
                    k = _key(msg)
                    seen[k] += 1
                    events.append(msg.dict())
                    print(f"  rx: {msg}")
                time.sleep(0.004)
    except KeyboardInterrupt:
        print("\n[stopped]")

    print("\n=== UNIQUE EVENT KINDS (count) ===")
    for k, n in sorted(seen.items()):
        print(f"  {k:32s} x{n}")

    # Collect the note-on notes seen on each channel — this is the pad map.
    note_channels: dict[int, set[int]] = {}
    for e in events:
        if e.get("type") == "note_on" and e.get("velocity", 0) > 0:
            note_channels.setdefault(e["channel"], set()).add(e["note"])
    print("\n=== NOTE-ON notes per MIDI channel (1-indexed) ===")
    for ch in sorted(note_channels):
        notes = sorted(note_channels[ch])
        print(f"  ch{ch + 1}: {notes}  ({len(notes)} distinct)")

    with open(LOG_PATH, "w") as fh:
        json.dump({"unique": dict(seen), "events": events}, fh, indent=2)
    print(f"\n[ok] wrote {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
