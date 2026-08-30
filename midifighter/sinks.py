"""LED output sinks — swappable render targets for the animation engine.

The engine emits per-pad color velocities; a sink decides where they go:

    DeviceSink   -> the real Midi Fighter 3D (needs 4-Banks Mode disabled)
    TerminalSink -> an ANSI 4x4 grid in the terminal (works today, no hardware)

Both share the LedSink interface, so an animation runs unchanged against either.
This lets the whole light show be built and tested before the LEDs are unblocked.
"""

from __future__ import annotations

import sys

from . import protocol as p

GRID = 16
COLS = 4


def _dim(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """Scale an RGB triple by factor, clamped to 0..255."""
    return tuple(max(0, min(255, round(c * factor))) for c in rgb)  # type: ignore


class LedSink:
    """Abstract per-pad color sink. Velocities follow protocol.COLORS."""

    def set_color(self, pad: int, velocity: int) -> None:
        """Queue a color velocity for a pad (0..15)."""
        raise NotImplementedError

    def all_off(self) -> None:
        """Clear every pad."""
        raise NotImplementedError

    def flush(self, force: bool = False) -> int:
        """Push queued changes to the target. Returns pads written."""
        raise NotImplementedError

    def close(self) -> None:
        """Release resources (default: clear)."""
        self.all_off()
        self.flush(force=True)


class DeviceSink(LedSink):
    """Drives the physical Midi Fighter 3D via a MidiFighter3D instance.

    Args:
        device: An opened MidiFighter3D. The sink uses its delta-only,
            rate-limited flush so animations never flood the endpoint.
    """

    def __init__(self, device) -> None:
        self._dev = device

    def set_color(self, pad: int, velocity: int) -> None:
        self._dev.queue_color(pad, velocity)

    def all_off(self) -> None:
        self._dev.all_off()

    def flush(self, force: bool = False) -> int:
        return self._dev.flush(force=force)


class TerminalSink(LedSink):
    """Renders the 4x4 grid as ANSI truecolor blocks in the terminal.

    A dim palette color renders darker; velocity 0 renders as an unlit cell.
    Redraws in place each flush so an animation loop looks smooth.

    Args:
        stream: Output stream (defaults to sys.stdout).
        cell: Characters per pad cell width (visual size).
    """

    def __init__(self, stream=None, cell: int = 6) -> None:
        self._out = stream or sys.stdout
        self._cell = cell
        self._grid = [0] * GRID          # current velocities
        self._pending = [0] * GRID
        self._drawn_once = False

    def set_color(self, pad: int, velocity: int) -> None:
        self._pending[pad] = velocity

    def all_off(self) -> None:
        for i in range(GRID):
            self._pending[i] = 0

    def _cell_rgb(self, velocity: int) -> tuple[int, int, int]:
        name, bright = p.velocity_to_color(velocity)
        if name is None:
            return (30, 30, 34)          # unlit
        rgb = p.COLOR_RGB[name]
        return rgb if bright else _dim(rgb, 0.40)

    def flush(self, force: bool = False) -> int:
        changed = sum(1 for i in range(GRID) if self._grid[i] != self._pending[i])
        if changed == 0 and not force and self._drawn_once:
            return 0
        self._grid = list(self._pending)
        lines = []
        if not self._drawn_once:
            lines.append("\x1b[2J")       # clear once
        lines.append("\x1b[H")            # cursor home
        pad_w = " " * self._cell
        for row in range(COLS):
            cells = []
            for col in range(COLS):
                r, g, b = self._cell_rgb(self._grid[row * COLS + col])
                cells.append(f"\x1b[48;2;{r};{g};{b}m{pad_w}\x1b[0m")
            line = " ".join(cells)
            lines.append(line)
            lines.append("")             # blank spacer row
        self._out.write("\n".join(lines) + "\n")
        self._out.flush()
        self._drawn_once = True
        return changed
