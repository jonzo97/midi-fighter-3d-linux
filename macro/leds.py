"""LED feedback for the macro controller — turns the grid into a control surface.

Behaviour:
    - Switching layer (bank button) repaints the grid: pads that have an action
      on the active layer glow in that layer's DIM color; unmapped pads go dark.
    - Pressing a mapped pad flashes it BRIGHT (same hue) then restores to dim,
      so you get tactile-plus-visual confirmation an action fired.

All renders are serialized behind a lock so the MIDI input thread and the flash
restore timers never interleave bytes on the output port. Palette-safe: base is
the dim band, flash is the bright band of the same hue (never the special
121-127 "active color" range).
"""

from __future__ import annotations

import threading
from typing import Optional

from midifighter import protocol as p
from midifighter.sinks import LedSink

GRID = 16
FLASH_MS = 140


class LayerLeds:
    """Drives per-layer LED feedback through an LedSink.

    Args:
        sink: The LedSink to render to (DeviceSink in normal use).
        flash_ms: Bright-flash duration before restoring to the dim base.
    """

    def __init__(self, sink: LedSink, flash_ms: int = FLASH_MS) -> None:
        self._sink = sink
        self._flash = max(0.02, flash_ms / 1000.0)
        self._lock = threading.Lock()
        self._layer = None
        self._base: dict[int, int] = {pad: p.COLOR_OFF for pad in range(GRID)}
        self._timers: dict[int, threading.Timer] = {}

    def on_layer(self, layer) -> None:
        """Repaint the whole grid for a newly active layer."""
        with self._lock:
            self._layer = layer
            dim = p.color_velocity(layer.color, bright=False)
            self._base = {
                pad: (dim if pad in layer.pads else p.COLOR_OFF)
                for pad in range(GRID)
            }
            self._render_all_locked()

    def on_fire(self, pad: int) -> None:
        """Flash a mapped pad bright, then schedule its restore to dim."""
        with self._lock:
            if self._layer is None or pad not in self._layer.pads:
                return
            bright = p.color_velocity(self._layer.color, bright=True)
            self._sink.set_color(pad, bright)
            self._sink.flush(force=True)
            old = self._timers.pop(pad, None)
        if old is not None:
            old.cancel()
        timer = threading.Timer(self._flash, self._restore, args=(pad,))
        timer.daemon = True
        with self._lock:
            self._timers[pad] = timer
        timer.start()

    def clear(self) -> None:
        """Turn the whole grid off and cancel pending restores."""
        with self._lock:
            for t in self._timers.values():
                t.cancel()
            self._timers.clear()
            self._sink.all_off()
            self._sink.flush(force=True)

    # --- internals ----------------------------------------------------------
    def _restore(self, pad: int) -> None:
        with self._lock:
            self._sink.set_color(pad, self._base.get(pad, p.COLOR_OFF))
            self._sink.flush(force=True)
            self._timers.pop(pad, None)

    def _render_all_locked(self) -> None:
        for pad, vel in self._base.items():
            self._sink.set_color(pad, vel)
        self._sink.flush(force=True)
