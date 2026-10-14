"""Driver: Four Banks Mode pad notes fold onto the grid; input-only open.

unittest-style, no hardware (mido ports are mocked).
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mido  # noqa: E402

from midifighter import protocol as p  # noqa: E402
from midifighter.device import ButtonDown, ButtonUp, MidiFighter3D  # noqa: E402


class TestDriverFold(unittest.TestCase):
    def test_four_banks_mode_notes_fold_onto_grid(self):
        mf = MidiFighter3D(pad_notes=list(range(36, 52)))
        ch = p.to_mido(p.INPUT_CHANNEL)
        ev = mf._decode(mido.Message("note_on", channel=ch, note=84, velocity=127))
        self.assertEqual(ev, ButtonDown(pad=0, note=84, velocity=127))
        ev = mf._decode(mido.Message("note_on", channel=ch, note=99, velocity=127))
        self.assertEqual(ev.pad, 15)
        ev = mf._decode(mido.Message("note_off", channel=ch, note=60))
        self.assertEqual(ev, ButtonUp(pad=8, note=60))
        self.assertIsNone(mf._decode(
            mido.Message("note_on", channel=ch, note=100, velocity=127)))

    def test_input_only_open_never_writes_leds(self):
        from unittest import mock
        import midifighter.device as dev

        class In:
            def close(self):
                pass

        with mock.patch.object(dev, "find_input_name", return_value="MF in"), \
                mock.patch.object(dev, "find_output_name", return_value="MF out"), \
                mock.patch.object(dev.mido, "open_input", return_value=In()) as oi, \
                mock.patch.object(dev.mido, "open_output") as oo:
            mf = MidiFighter3D(pad_notes=list(range(36, 52))).open(output=False)
            mf.close()
        oi.assert_called_once()
        oo.assert_not_called()


if __name__ == "__main__":
    unittest.main()
