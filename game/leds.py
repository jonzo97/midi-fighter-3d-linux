"""Device LED cueing for the rhythm game.

Maps the 4 lanes to 4 target pads (the bottom row: notes 36-39). Each frame the
target pad brightens as its next note approaches the hit line; on a judgment the
pad flashes green (perfect/great), yellow (good), or red (miss). Reuses the LED
sink + delta/rate-limited flushing so it never floods the device.

Orientation note: bottom row = pads 0-3 was inferred from the note-36=bottom
probe. If the mapping looks rotated on your unit, pass a different target_pads
list (a calibration step can lock this exactly later).
"""

from __future__ import annotations

from typing import Optional

from midifighter import protocol as p
from midifighter.sinks import LedSink
from .engine import GameEngine, Judgement

# Bottom row target pad per lane (notes 36-39).
DEFAULT_TARGETS = [0, 1, 2, 3]
APPROACH_MS = 1500          # how early a note starts lighting its pad
FLASH_MS = 130

_FLASH_COLOR = {
    Judgement.PERFECT: "green",
    Judgement.GREAT: "green",
    Judgement.GOOD: "yellow",
    Judgement.MISS: "red",
}


class GameLeds:
    """Per-lane LED cueing driven by the game engine.

    Args:
        sink: LedSink to render to (DeviceSink in normal use).
        lanes: Number of lanes.
        target_pads: Pad index per lane (defaults to the bottom row).
        approach_ms: Lead time over which a pad ramps to full brightness.
    """

    def __init__(self, sink: LedSink, lanes: int = 4,
                 target_pads: Optional[list[int]] = None,
                 approach_ms: int = APPROACH_MS) -> None:
        self._sink = sink
        self.lanes = lanes
        self._targets = target_pads or DEFAULT_TARGETS[:lanes]
        self._approach = approach_ms
        self._flash_until: dict[int, int] = {}   # lane -> expiry song time
        self._flash_color: dict[int, str] = {}

    def on_judgement(self, lane: int, judgement: Judgement, t_ms: int) -> None:
        """Register a judgment flash for a lane."""
        self._flash_until[lane] = t_ms + FLASH_MS
        self._flash_color[lane] = _FLASH_COLOR[judgement]

    def render(self, engine: GameEngine, t_ms: int) -> None:
        """Compute and push this frame's LED state for all lane targets."""
        for lane in range(self.lanes):
            pad = self._targets[lane]
            vel = self._lane_velocity(engine, lane, t_ms)
            self._sink.set_color(pad, vel)
        self._sink.flush()

    def clear(self) -> None:
        """Turn off all lane target pads."""
        for pad in self._targets:
            self._sink.set_color(pad, p.COLOR_OFF)
        self._sink.flush(force=True)

    # --- internals ----------------------------------------------------------
    def _lane_velocity(self, engine: GameEngine, lane: int, t_ms: int) -> int:
        # Active judgment flash wins.
        if self._flash_until.get(lane, 0) > t_ms:
            return p.color_velocity(self._flash_color[lane], bright=True)
        # Otherwise ramp on the next approaching note.
        nxt = engine.next_in_lane(lane, t_ms)
        if nxt is None:
            return p.COLOR_OFF
        dt = nxt.note.time_ms - t_ms
        if dt > self._approach or dt < -engine.good_window:
            return p.COLOR_OFF
        # Near the hit line -> bright; far -> dim.
        proximity = 1.0 - max(0, dt) / self._approach
        return p.color_velocity("cyan", bright=proximity > 0.6)
