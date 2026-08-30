"""Offline unit tests for the MidiFighter3D driver logic (no hardware).

Exercises input decoding, LED color encoding, delta-only flushing, and grid
geometry against a fake output port so the wire behaviour is verified without a
connected device.
"""

from __future__ import annotations

import os
import sys

import mido

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from midifighter import protocol as p  # noqa: E402
from midifighter.device import (  # noqa: E402
    BankButton,
    ButtonDown,
    ButtonUp,
    MidiFighter3D,
    Rotate,
    SideButton,
    Tilt,
)

# Fixed, known pad map so tests don't depend on capture state.
PADS = list(range(36, 52))


class FakeOut:
    """Records every mido Message sent to it."""

    def __init__(self) -> None:
        self.sent: list[mido.Message] = []

    def send(self, msg: mido.Message) -> None:
        self.sent.append(msg)


def make_driver() -> tuple[MidiFighter3D, FakeOut]:
    mf = MidiFighter3D(pad_notes=PADS)
    fake = FakeOut()
    mf._out = fake  # inject fake output; no real port opened
    return mf, fake


# --- input decoding ---------------------------------------------------------
def test_decode_button_down():
    mf, _ = make_driver()
    msg = mido.Message("note_on", channel=p.to_mido(p.INPUT_CHANNEL),
                       note=38, velocity=127)
    ev = mf._decode(msg)
    assert isinstance(ev, ButtonDown)
    assert ev.pad == 2 and ev.note == 38 and ev.velocity == 127


def test_decode_button_up_via_note_off():
    mf, _ = make_driver()
    msg = mido.Message("note_off", channel=p.to_mido(p.INPUT_CHANNEL), note=36)
    ev = mf._decode(msg)
    assert isinstance(ev, ButtonUp) and ev.pad == 0


def test_decode_button_up_via_zero_velocity():
    mf, _ = make_driver()
    msg = mido.Message("note_on", channel=p.to_mido(p.INPUT_CHANNEL),
                       note=51, velocity=0)
    ev = mf._decode(msg)
    assert isinstance(ev, ButtonUp) and ev.pad == 15


def test_decode_tilt_forward():
    mf, _ = make_driver()
    msg = mido.Message("control_change", channel=p.to_mido(p.MOTION_CHANNEL),
                       control=p.TILT_FORWARD_CC, value=64)
    ev = mf._decode(msg)
    assert isinstance(ev, Tilt) and ev.edge == "forward" and ev.value == 64


def test_decode_rotate_maps_to_pad():
    mf, _ = make_driver()
    # CC number equals a pad note (40 -> pad index 4 with PADS starting at 36).
    msg = mido.Message("control_change", channel=p.to_mido(p.MOTION_CHANNEL),
                       control=40, value=1)
    ev = mf._decode(msg)
    assert isinstance(ev, Rotate) and ev.control == 40 and ev.pad == 4


def test_decode_bank_button():
    mf, _ = make_driver()
    # Bank 1 = note 0 on the motion channel.
    msg = mido.Message("note_on", channel=p.to_mido(p.MOTION_CHANNEL),
                       note=0, velocity=127)
    ev = mf._decode(msg)
    assert isinstance(ev, BankButton) and ev.index == 1


def test_decode_side_button():
    mf, _ = make_driver()
    # First side button = note 38 on the motion channel.
    msg = mido.Message("note_on", channel=p.to_mido(p.MOTION_CHANNEL),
                       note=38, velocity=127)
    ev = mf._decode(msg)
    assert isinstance(ev, SideButton) and ev.index == 0


def test_decode_ignores_foreign_channel():
    mf, _ = make_driver()
    msg = mido.Message("note_on", channel=0, note=38, velocity=100)
    assert mf._decode(msg) is None


# --- output encoding --------------------------------------------------------
def test_set_color_sends_correct_note_and_velocity():
    mf, fake = make_driver()
    mf.set_color(2, "red")  # pad 2 -> note 38, bright red vel 13
    assert len(fake.sent) == 1
    m = fake.sent[0]
    assert m.type == "note_on"
    assert m.channel == p.to_mido(p.COLOR_CHANNEL)
    assert m.note == 38
    assert m.velocity == 13


def test_all_off_clears_color_and_anim_for_16_pads():
    mf, fake = make_driver()
    mf.all_off()
    # 16 color-off + 16 anim-off = 32 messages, all velocity 0.
    assert len(fake.sent) == 32
    assert all(m.velocity == 0 for m in fake.sent)


# --- delta-only flushing ----------------------------------------------------
def test_flush_sends_only_changed_pads():
    mf, fake = make_driver()
    mf.queue_color(0, 13)
    mf.queue_color(1, 85)
    assert mf.flush(force=True) == 2
    fake.sent.clear()
    # Re-queue same colors -> no delta -> nothing sent.
    mf.queue_color(0, 13)
    mf.queue_color(1, 85)
    assert mf.flush(force=True) == 0
    assert fake.sent == []


def test_flush_rate_limited_without_force():
    mf, fake = make_driver()
    mf.queue_color(0, 13)
    mf.flush(force=True)          # establishes last_flush time
    mf.queue_color(1, 85)
    # Immediate second flush without force is rate-limited to 0 writes.
    assert mf.flush(force=False) == 0


# --- geometry ---------------------------------------------------------------
def test_geometry_roundtrip():
    for pad in range(16):
        x, y = MidiFighter3D.pad_to_xy(pad)
        assert MidiFighter3D.xy_to_pad(x, y) == pad
    assert MidiFighter3D.pad_to_xy(0) == (0, 0)
    assert MidiFighter3D.pad_to_xy(15) == (3, 3)
    assert MidiFighter3D.xy_to_pad(3, 0) == 3
