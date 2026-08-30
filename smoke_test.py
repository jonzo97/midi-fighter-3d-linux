#!/usr/bin/env python3
"""Phase 0 smoke test for the Midi Fighter 3D.

Confirms the full connection layer works end-to-end before any driver code:
  1. Lists every MIDI port on the system.
  2. Resolves the Midi Fighter 3D in/out ports BY NAME (dynamic, not hw:2).
  3. Sends a verified color command (bright red on pad note 60) then clears it.
  4. Opens the input port and prints any pad/tilt events for a few seconds.

Run inside the project venv:
    . .venv/bin/activate && python smoke_test.py
"""

from __future__ import annotations

import sys
import time

import mido

from midifighter.ports import (
    DeviceNotFoundError,
    find_input_name,
    find_output_name,
)

# Verified in research: Note On, channel byte 0x92 (mido channel index 2 = MIDI
# ch 3), note 0x3C (60), velocity 0x0D (13) => bright red. amidi confirmed the
# device accepts this write. Velocity 0 releases the MIDI LED override.
COLOR_CHANNEL = 2      # mido 0-indexed == MIDI channel 3 (device base channel)
PROBE_NOTE = 60        # 0x3C, one arcade pad's note per the user guide example
BRIGHT_RED_VELOCITY = 13
LISTEN_SECONDS = 5.0


def list_ports() -> None:
    """Print all input and output MIDI ports for visibility."""
    print("=== Input ports ===")
    for name in mido.get_input_names():
        print(f"  in : {name}")
    print("=== Output ports ===")
    for name in mido.get_output_names():
        print(f"  out: {name}")
    print()


def test_output() -> bool:
    """Send a bright-red color command then clear it.

    Returns:
        bool: True if the command was sent without error.
    """
    try:
        out_name = find_output_name()
    except DeviceNotFoundError as exc:
        print(f"[FAIL] output: {exc}")
        return False

    print(f"[ok] output port: {out_name}")
    with mido.open_output(out_name) as port:
        port.send(mido.Message(
            "note_on",
            channel=COLOR_CHANNEL,
            note=PROBE_NOTE,
            velocity=BRIGHT_RED_VELOCITY,
        ))
        print(f"[ok] sent bright-red to note {PROBE_NOTE} (watch the grid)")
        time.sleep(1.0)
        # Release the MIDI LED override (velocity 0).
        port.send(mido.Message(
            "note_on", channel=COLOR_CHANNEL, note=PROBE_NOTE, velocity=0
        ))
        print("[ok] cleared color override")
    return True


def test_input() -> bool:
    """Open the input port and print events for LISTEN_SECONDS.

    Returns:
        bool: True if the input port opened (events are optional — the user
        may not be at the device).
    """
    try:
        in_name = find_input_name()
    except DeviceNotFoundError as exc:
        print(f"[FAIL] input: {exc}")
        return False

    print(f"[ok] input port: {in_name}")
    print(f"     press pads / tilt the device for {LISTEN_SECONDS:.0f}s ...")
    count = 0
    with mido.open_input(in_name) as port:
        deadline = time.monotonic() + LISTEN_SECONDS
        while time.monotonic() < deadline:
            for msg in port.iter_pending():
                count += 1
                print(f"     rx: {msg}")
            time.sleep(0.005)
    print(f"[ok] received {count} message(s)")
    return True


def main() -> int:
    """Run the smoke test. Returns process exit code."""
    print(f"mido backend: {mido.backend}\n")
    list_ports()
    out_ok = test_output()
    in_ok = test_input()
    print()
    if out_ok and in_ok:
        print("SMOKE TEST PASSED — connection layer is live.")
        return 0
    print("SMOKE TEST FAILED — see [FAIL] lines above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
