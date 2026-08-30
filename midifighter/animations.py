"""Frame-based LED animation engine for the Midi Fighter 3D.

Animations are pure-ish generators: each ``update(t, dt, pressed)`` returns a
``{pad: color_velocity}`` map for the current frame. The Engine drives them at a
fixed rate against any LedSink (real device or terminal simulator) and, when a
device is attached, feeds real pad-press state in — so reactive animations work
today even though LED *output* to the hardware is still gated behind 4-Banks
Mode. Render to TerminalSink now; swap to DeviceSink after the one-time unblock.

Key components:
    Animation subclasses -- Reactive, RainbowSweep, Ripple
    Engine               -- input + timing loop -> sink
"""

from __future__ import annotations

import time
from typing import Optional

from . import protocol as p
from .sinks import LedSink

GRID = 16
COLS = 4
FPS = 60.0


def _pad_xy(pad: int) -> tuple[int, int]:
    return pad % COLS, pad // COLS


class Animation:
    """Base animation. Override update(); return {pad: velocity}."""

    name = "base"

    def update(self, t: float, dt: float, pressed: set[int]) -> dict[int, int]:
        """Compute this frame.

        Args:
            t: Seconds since the animation started.
            dt: Seconds since the previous frame.
            pressed: Pad indices (0..15) currently held.

        Returns:
            dict[int, int]: pad -> color velocity for changed pads.
        """
        raise NotImplementedError

    def on_press(self, pad: int) -> None:
        """Optional hook for press-triggered effects."""


class Reactive(Animation):
    """Held pads glow bright; on release they fade dim then off."""

    name = "reactive"

    def __init__(self, color: str = "cyan", fade: float = 0.6) -> None:
        self._color = color
        self._fade = fade
        self._level = [0.0] * GRID   # 0..1 brightness memory per pad

    def update(self, t: float, dt: float, pressed: set[int]) -> dict[int, int]:
        out = {}
        for pad in range(GRID):
            if pad in pressed:
                self._level[pad] = 1.0
            else:
                self._level[pad] = max(0.0, self._level[pad] - dt / self._fade)
            lvl = self._level[pad]
            if lvl <= 0.0:
                out[pad] = p.COLOR_OFF
            elif lvl > 0.5:
                out[pad] = p.color_velocity(self._color, bright=True)
            else:
                out[pad] = p.color_velocity(self._color, bright=False)
        return out


class RainbowSweep(Animation):
    """A hue wipe travels diagonally across the 4x4 grid."""

    name = "rainbow"

    def __init__(self, speed: float = 1.5) -> None:
        self._speed = speed

    def update(self, t: float, dt: float, pressed: set[int]) -> dict[int, int]:
        out = {}
        hues = p.HUE_ORDER
        for pad in range(GRID):
            x, y = _pad_xy(pad)
            phase = (x + y) / (2 * (COLS - 1))          # 0..1 diagonal
            idx = int((phase + t * self._speed) * len(hues)) % len(hues)
            bright = pad in pressed or True
            out[pad] = p.color_velocity(hues[idx], bright=bright)
        return out


class Ripple(Animation):
    """Press a pad -> an expanding ring of color radiates from it."""

    name = "ripple"

    def __init__(self, color: str = "magenta", speed: float = 6.0,
                 width: float = 0.9) -> None:
        self._color = color
        self._speed = speed
        self._width = width
        self._ripples: list[tuple[int, float]] = []   # (origin pad, start t)
        self._t = 0.0

    def on_press(self, pad: int) -> None:
        self._ripples.append((pad, self._t))

    def update(self, t: float, dt: float, pressed: set[int]) -> dict[int, int]:
        self._t = t
        out = {pad: p.COLOR_OFF for pad in range(GRID)}
        # Drop ripples older than the grid diagonal can hold.
        self._ripples = [(o, s) for (o, s) in self._ripples if t - s < 1.5]
        for origin, start in self._ripples:
            ox, oy = _pad_xy(origin)
            radius = (t - start) * self._speed
            for pad in range(GRID):
                x, y = _pad_xy(pad)
                dist = ((x - ox) ** 2 + (y - oy) ** 2) ** 0.5
                if abs(dist - radius) <= self._width:
                    out[pad] = p.color_velocity(self._color, bright=True)
        for pad in pressed:
            out[pad] = p.color_velocity("white", bright=True)
        return out


class Engine:
    """Runs an animation against a sink, optionally fed by real pad input.

    Args:
        sink: Where LED frames render (DeviceSink or TerminalSink).
        device: Optional opened MidiFighter3D for live pad input. Its on_event
            is hijacked to track pressed pads and forward presses to the
            animation's on_press hook.
        fps: Target frame rate.
    """

    def __init__(self, sink: LedSink, device=None, fps: float = FPS) -> None:
        self._sink = sink
        self._device = device
        self._fps = fps
        self._pressed: set[int] = set()
        self._anim: Optional[Animation] = None
        if device is not None:
            device.on_event = self._on_event

    def _on_event(self, ev) -> None:
        # Local import avoids a hard dependency when device is absent.
        from .device import ButtonDown, ButtonUp
        if isinstance(ev, ButtonDown):
            self._pressed.add(ev.pad)
            if self._anim is not None:
                self._anim.on_press(ev.pad)
        elif isinstance(ev, ButtonUp):
            self._pressed.discard(ev.pad)

    def step(self, anim: Animation, t: float, dt: float) -> int:
        """Advance one frame; returns pads written by the sink."""
        self._anim = anim
        frame = anim.update(t, dt, set(self._pressed))
        for pad, vel in frame.items():
            self._sink.set_color(pad, vel)
        return self._sink.flush()

    def run(self, anim: Animation, duration: float) -> None:
        """Run an animation for ``duration`` seconds at the target FPS."""
        self._anim = anim
        frame_dt = 1.0 / self._fps
        start = time.monotonic()
        prev = start
        try:
            while (now := time.monotonic()) - start < duration:
                self.step(anim, now - start, now - prev)
                prev = now
                time.sleep(frame_dt)
        finally:
            self._sink.all_off()
            self._sink.flush(force=True)
