"""Offline tests for macro LED feedback (no hardware, no real timers).

Timers are given a huge flash duration so they never fire mid-test; restore is
invoked directly to verify the dim<->bright transition.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from midifighter import protocol as p  # noqa: E402
from midifighter.sinks import LedSink  # noqa: E402
from macro.config import load_config  # noqa: E402
from macro.leds import LayerLeds  # noqa: E402

CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "macro", "config.toml")


class FakeSink(LedSink):
    """Records the last color velocity per pad."""

    def __init__(self):
        self.grid = {i: None for i in range(16)}
        self.flushes = 0
        self.offs = 0

    def set_color(self, pad, velocity):
        self.grid[pad] = velocity

    def all_off(self):
        self.offs += 1
        self.grid = {i: 0 for i in range(16)}

    def flush(self, force=False):
        self.flushes += 1
        return 0


def _layer():
    return load_config(CONFIG).layers["sway"]


def test_on_layer_paints_mapped_dim_unmapped_off():
    layer = _layer()
    sink = FakeSink()
    leds = LayerLeds(sink)
    leds.on_layer(layer)
    dim = p.color_velocity(layer.color, bright=False)
    for pad in range(16):
        expected = dim if pad in layer.pads else p.COLOR_OFF
        assert leds._base[pad] == expected
        assert sink.grid[pad] == expected


def test_on_fire_flashes_bright_then_restores():
    layer = _layer()
    sink = FakeSink()
    leds = LayerLeds(sink, flash_ms=10_000_000)   # timer won't fire in-test
    leds.on_layer(layer)
    pad = next(iter(layer.pads))
    leds.on_fire(pad)
    assert sink.grid[pad] == p.color_velocity(layer.color, bright=True)
    leds._restore(pad)
    assert sink.grid[pad] == p.color_velocity(layer.color, bright=False)
    leds.clear()


def test_on_fire_ignores_unmapped_pad():
    layer = _layer()
    sink = FakeSink()
    leds = LayerLeds(sink)
    leds.on_layer(layer)
    unmapped = next(pad for pad in range(16) if pad not in layer.pads)
    before = sink.grid[unmapped]
    leds.on_fire(unmapped)
    assert sink.grid[unmapped] == before      # untouched


def test_clear_turns_off_and_cancels():
    layer = _layer()
    sink = FakeSink()
    leds = LayerLeds(sink, flash_ms=10_000_000)
    leds.on_layer(layer)
    leds.on_fire(next(iter(layer.pads)))
    leds.clear()
    assert sink.offs >= 1
    assert leds._timers == {}


def test_layers_get_distinct_colors():
    cfg = load_config(CONFIG)
    colors = [layer.color for layer in cfg.layers.values()]
    assert all(isinstance(c, str) for c in colors)
    assert len(set(colors)) >= 2                # not all the same
