#!/usr/bin/env python3
"""Definitive 4-Banks Mode test for the Midi Fighter 3D.

In 4-Banks Mode the 16 pads emit a DIFFERENT note set per bank (up to 64 notes
across 4 banks). If banks mode is OFF, a pad emits the same note regardless of
bank. This tool watches you switch banks and press pads, then reports the note
set seen under each bank — turning the "is 4-Banks Mode on?" question into a
measured yes/no.

Procedure (follow the on-screen prompts):
    press BANK 1 button, then press a few pads;
    press BANK 2 button, then the same pads;
    ... banks 3 and 4; Ctrl-C when done.

Run:
    . .venv/bin/activate && python tools/diag_banks.py
"""

from __future__ import annotations

import os
import sys
import time
from collections import defaultdict

import mido

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from midifighter import protocol as p  # noqa: E402
from midifighter.ports import DeviceNotFoundError, find_input_name  # noqa: E402

# Bank buttons emit these notes on the motion channel (ch 4).
BANK_BUTTON_NOTES = set(p.BANK_NOTES.values())  # {0,1,2,3}
MOTION_CH0 = p.to_mido(p.MOTION_CHANNEL)
INPUT_CH0 = p.to_mido(p.INPUT_CHANNEL)


def main() -> int:
    """Run the banks-mode discriminator. Returns exit code."""
    try:
        in_name = find_input_name()
    except DeviceNotFoundError as exc:
        print(f"[FAIL] {exc}")
        return 1

    print(f"[ok] listening on: {in_name}")
    print("     Press BANK 1, then some pads. Then BANK 2 + same pads. "
          "Banks 3, 4. Ctrl-C when done.\n")

    current_bank = "unknown"
    per_bank: dict[str, set[int]] = defaultdict(set)

    try:
        with mido.open_input(in_name) as port:
            while True:
                for msg in port.iter_pending():
                    ch = getattr(msg, "channel", None)
                    if msg.type == "note_on" and msg.velocity > 0:
                        if ch == MOTION_CH0 and msg.note in BANK_BUTTON_NOTES:
                            # Bank note 0->bank1, etc.
                            current_bank = f"bank{msg.note + 1}"
                            print(f"  -> switched to {current_bank}")
                        elif ch == INPUT_CH0:
                            per_bank[current_bank].add(msg.note)
                            print(f"     [{current_bank}] pad note {msg.note}")
                time.sleep(0.004)
    except KeyboardInterrupt:
        print("\n[stopped]\n")

    print("=== pad notes seen per bank ===")
    for bank in sorted(per_bank):
        notes = sorted(per_bank[bank])
        print(f"  {bank}: {notes}")

    # Verdict: if two banks share pad presses but map to different notes,
    # 4-Banks Mode is ON. If only one bank context or identical sets, it's off.
    real_banks = {b: n for b, n in per_bank.items() if b != "unknown" and n}
    print("\n=== VERDICT ===")
    if len(real_banks) >= 2:
        note_sets = list(real_banks.values())
        if any(a != b for a in note_sets for b in note_sets):
            print("  4-BANKS MODE IS ON — pads remap per bank. LEDs are blocked")
            print("  over MIDI until this is disabled (Utility / SysEx / Wine).")
        else:
            print("  Banks emit identical notes — 4-Banks Mode likely OFF.")
    else:
        print("  Not enough bank switches captured. Re-run and press bank "
              "buttons 1-4 with pad presses between each.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
