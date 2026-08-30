"""Offline tests for the color reverse-lookup, sinks, and animation engine.

No hardware, no real-time loop — animations are stepped directly and sinks
render to an in-memory buffer.
"""

from __future__ import annotations

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from midifighter import protocol as p  # noqa: E402
from midifighter.animations import Engine, RainbowSweep, Reactive, Ripple  # noqa: E402
from midifighter.sinks import DeviceSink, TerminalSink  # noqa: E402


# --- color reverse lookup ---------------------------------------------------
def test_velocity_color_roundtrip():
    for name in p.HUE_ORDER:
        for bright in (True, False):
            vel = p.color_velocity(name, bright)
            got_name, got_bright = p.velocity_to_color(vel)
            assert got_name == name
            assert got_bright == bright


def test_velocity_zero_is_off():
    assert p.velocity_to_color(0) == (None, False)


def test_velocity_white_edges():
    assert p.velocity_to_color(5) == ("white", False)
    assert p.velocity_to_color(125) == ("white", True)


# --- animations produce valid velocities ------------------------------------
def _valid(frame):
    return all(0 <= v <= 127 for v in frame.values())


def test_reactive_pressed_then_faded():
    a = Reactive(color="cyan", fade=0.5)
    on = a.update(0.0, 0.016, pressed={3})
    assert on[3] == p.color_velocity("cyan", bright=True)
    assert _valid(on)
    # Release and fade well past the fade time -> off.
    a.update(0.1, 0.016, pressed=set())
    off = a.update(1.0, 1.0, pressed=set())
    assert off[3] == p.COLOR_OFF


def test_rainbow_covers_grid():
    a = RainbowSweep()
    frame = a.update(0.5, 0.016, pressed=set())
    assert len(frame) == 16
    assert _valid(frame)


def test_ripple_lights_on_press():
    a = Ripple(color="magenta", speed=6.0)
    a._t = 0.0
    a.on_press(5)
    # A little later the ring has expanded and lit some non-origin pads.
    frame = a.update(0.15, 0.016, pressed=set())
    assert _valid(frame)
    assert any(v != p.COLOR_OFF for v in frame.values())


# --- sinks ------------------------------------------------------------------
def test_terminal_sink_renders_and_counts_changes():
    buf = io.StringIO()
    sink = TerminalSink(stream=buf)
    sink.set_color(0, p.color_velocity("red"))
    sink.set_color(15, p.color_velocity("blue"))
    changed = sink.flush(force=True)
    assert changed == 2
    out = buf.getvalue()
    assert "\x1b[48;2;" in out          # truecolor escape emitted


class FakeDevice:
    def __init__(self):
        self.queued = {}
        self.flushed = 0
        self.offed = 0

    def queue_color(self, pad, vel):
        self.queued[pad] = vel

    def flush(self, force=False):
        n = len(self.queued)
        self.flushed += 1
        return n

    def all_off(self):
        self.offed += 1


def test_device_sink_delegates():
    dev = FakeDevice()
    sink = DeviceSink(dev)
    sink.set_color(2, 13)
    assert dev.queued == {2: 13}
    assert sink.flush(force=True) == 1
    sink.all_off()
    assert dev.offed == 1


# --- engine step ------------------------------------------------------------
def test_engine_step_writes_frame():
    buf = io.StringIO()
    sink = TerminalSink(stream=buf)
    engine = Engine(sink, device=None)
    a = RainbowSweep()
    written = engine.step(a, t=0.0, dt=0.016)
    assert written == 16            # first frame: all cells change from off
