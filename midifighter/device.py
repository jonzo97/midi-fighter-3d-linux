"""MidiFighter3D driver — high-level I/O over the class-compliant USB-MIDI unit.

Wraps mido's rtmidi backend with a device-shaped API: decoded input events
(button/tilt/rotate) delivered via callback, and palette-aware LED output with
delta-only, rate-limited flushing so a 60 Hz animation loop never floods the
bulk endpoint.

The wire details live in protocol.py; this module is pure logic and is unit
testable without hardware (see tests/). All note/channel numbers are sourced
from protocol constants, so once Phase-1 capture upgrades PAD_NOTES the driver
follows automatically.

Key components:
    Event dataclasses  -- ButtonDown/Up, Tilt, Rotate
    MidiFighter3D      -- open/close, on_event callback, set_color/set_grid/...
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import mido

from . import protocol as p
from .ports import find_input_name, find_output_name

# Minimum seconds between physical output flushes (rate limit ~60 Hz).
MIN_FLUSH_INTERVAL = 1.0 / 60.0

# Four Banks Mode (factory default) moves the pads to notes 52-67, 68-83 and
# 84-99 in banks 2-4. Those fold back onto the 16-pad grid so a layer works
# whichever device bank is lit (the Tower's midi.js folds the same way).
GRID_SIZE = 16
BANK_COUNT = 4


# --- Decoded input events ---------------------------------------------------
@dataclass(frozen=True)
class ButtonDown:
    """An arcade pad was pressed. ``pad`` is the 0..15 grid index."""
    pad: int
    note: int
    velocity: int


@dataclass(frozen=True)
class ButtonUp:
    """An arcade pad was released. ``pad`` is the 0..15 grid index."""
    pad: int
    note: int


@dataclass(frozen=True)
class Tilt:
    """Edge tilt on the motion sensor. ``edge`` in {left,forward,right,back}."""
    edge: str
    value: int


@dataclass(frozen=True)
class Rotate:
    """A pad was rotated (Pickup Mode). ``pad`` is the 0..15 grid index it maps
    to; ``value`` is the raw CC value. ``pad`` is None for unrecognised CCs."""
    control: int
    value: int
    pad: Optional[int] = None


@dataclass(frozen=True)
class BankButton:
    """A top bank button (1..4) was pressed. Useful as a macro-layer selector."""
    index: int          # 1..4


@dataclass(frozen=True)
class SideButton:
    """A side button (0..5) was pressed."""
    index: int          # 0..5


Event = object  # union of the above; kept loose for the callback signature

_EDGE_BY_CC = {
    p.TILT_LEFT_CC: "left",
    p.TILT_FORWARD_CC: "forward",
    p.TILT_RIGHT_CC: "right",
    p.TILT_BACK_CC: "back",
}
# note (on motion channel) -> bank index 1..4
_BANK_BY_NOTE = {note: idx for idx, note in p.BANK_NOTES.items()}
# note (on motion channel) -> side button index 0..5
_SIDE_BY_NOTE = {note: i for i, note in enumerate(p.SIDE_BUTTON_NOTES)}


class MidiFighter3D:
    """Driver for the DJ TechTools Midi Fighter 3D.

    Usage:
        def handle(ev): print(ev)
        with MidiFighter3D(on_event=handle) as mf:
            mf.set_color(0, "red")
            ...

    Args:
        on_event: Optional callback invoked from the MIDI input thread for each
            decoded event. Keep it fast; offload heavy work to your own queue.
        pad_notes: Override the pad note map (defaults to captured-or-candidate
            protocol.PAD_NOTES).
    """

    def __init__(
        self,
        on_event: Optional[Callable[[Event], None]] = None,
        pad_notes: Optional[list[int]] = None,
    ) -> None:
        self.on_event = on_event
        # Prefer captured pad notes if a Phase-1 log exists.
        self.pad_notes = pad_notes or p.load_captured_pad_notes() or list(p.PAD_NOTES)
        self._note_to_pad = {n: i for i, n in enumerate(self.pad_notes)}
        self._in: Optional[mido.ports.BaseInput] = None
        self._out: Optional[mido.ports.BaseOutput] = None
        # Output state: last color velocity sent per pad, for delta detection.
        self._last_color: dict[int, int] = {}
        self._pending: dict[int, int] = {}   # pad -> color velocity to flush
        self._last_flush = 0.0
        self._lock = threading.Lock()

    # --- lifecycle ----------------------------------------------------------
    def open(self, output: bool = True) -> "MidiFighter3D":
        """Open the ports by name and start the input callback.

        Args:
            output: Also open the output port (LEDs). With False the driver is
                input-only and never writes to the device, not even on close.

        Returns:
            MidiFighter3D: self, for chaining.

        Raises:
            DeviceNotFoundError: If the device's ports are not present.
        """
        in_name = find_input_name()
        if output:
            self._out = mido.open_output(find_output_name())
        self._in = mido.open_input(in_name, callback=self._on_midi)
        return self

    def close(self) -> None:
        """Clear the grid and close both ports."""
        try:
            if self._out is not None:
                self.all_off()
        finally:
            if self._in is not None:
                self._in.close()
                self._in = None
            if self._out is not None:
                self._out.close()
                self._out = None

    def __enter__(self) -> "MidiFighter3D":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    # --- input decoding -----------------------------------------------------
    def _on_midi(self, msg: mido.Message) -> None:
        """mido input callback: decode a raw message into an Event."""
        ev = self._decode(msg)
        if ev is not None and self.on_event is not None:
            self.on_event(ev)

    def _pad_for_note(self, note: int) -> Optional[int]:
        """Grid index for a pad note, folding Four Banks Mode banks 2-4 back."""
        pad = self._note_to_pad.get(note)
        if pad is not None:
            return pad
        first = self.pad_notes[0]
        last = first + GRID_SIZE * BANK_COUNT - 1
        if first + GRID_SIZE <= note <= last:
            return self._note_to_pad.get(first + (note - first) % GRID_SIZE)
        return None

    def _decode(self, msg: mido.Message) -> Optional[Event]:
        """Turn a raw mido Message into a decoded Event (or None to ignore)."""
        ch = getattr(msg, "channel", None)
        if msg.type == "note_on" and msg.velocity > 0 and ch == p.to_mido(p.INPUT_CHANNEL):
            pad = self._pad_for_note(msg.note)
            if pad is not None:
                return ButtonDown(pad=pad, note=msg.note, velocity=msg.velocity)
        elif (msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0)) \
                and ch == p.to_mido(p.INPUT_CHANNEL):
            pad = self._pad_for_note(msg.note)
            if pad is not None:
                return ButtonUp(pad=pad, note=msg.note)
        elif msg.type == "note_on" and msg.velocity > 0 and ch == p.to_mido(p.MOTION_CHANNEL):
            # Bank + side buttons share the motion channel.
            if msg.note in _BANK_BY_NOTE:
                return BankButton(index=_BANK_BY_NOTE[msg.note])
            if msg.note in _SIDE_BY_NOTE:
                return SideButton(index=_SIDE_BY_NOTE[msg.note])
        elif msg.type == "control_change" and ch == p.to_mido(p.MOTION_CHANNEL):
            edge = _EDGE_BY_CC.get(msg.control)
            if edge is not None:
                return Tilt(edge=edge, value=msg.value)
            # Per-pad rotation: CC number equals the pad's note number.
            return Rotate(control=msg.control, value=msg.value,
                          pad=self._note_to_pad.get(msg.control))
        return None

    # --- output -------------------------------------------------------------
    def _send(self, channel_1indexed: int, note: int, velocity: int) -> None:
        """Send one Note-On on a 1-indexed MIDI channel (no-op if closed)."""
        if self._out is None:
            return
        self._out.send(mido.Message(
            "note_on",
            channel=p.to_mido(channel_1indexed),
            note=note,
            velocity=velocity,
        ))

    def set_color(self, pad: int, color: str, bright: bool = True) -> None:
        """Set a pad's ring color immediately (bypasses the flush queue).

        Args:
            pad: Grid index 0..15.
            color: Palette color name (see protocol.COLORS).
            bright: Bright band if True, dim if False.
        """
        vel = p.color_velocity(color, bright)
        self._paint(pad, vel)

    def set_color_velocity(self, pad: int, velocity: int) -> None:
        """Set a pad color by raw velocity (advanced; see protocol tables)."""
        self._paint(pad, velocity)

    def _paint(self, pad: int, velocity: int) -> None:
        """Immediately send a color velocity to a pad and record it."""
        note = self.pad_notes[pad]
        self._send(p.COLOR_CHANNEL, note, velocity)
        with self._lock:
            self._last_color[pad] = velocity

    def clear(self, pad: int) -> None:
        """Release the LED override on one pad."""
        self._paint(pad, p.COLOR_OFF)

    def all_off(self) -> None:
        """Clear every pad's color and animation."""
        for pad, note in enumerate(self.pad_notes):
            self._send(p.COLOR_CHANNEL, note, p.COLOR_OFF)
            self._send(p.ANIM_CHANNEL, note, p.ANIM_OFF)
        with self._lock:
            self._last_color.clear()
            self._pending.clear()

    def set_animation(self, pad: int, velocity: int) -> None:
        """Set a pad's animation state (brightness/gate/pulse) by velocity.

        Args:
            pad: Grid index 0..15.
            velocity: An animation-band velocity (see protocol GATE/PULSE/etc).
        """
        self._send(p.ANIM_CHANNEL, self.pad_notes[pad], velocity)

    def set_brightness(self, pad: int, level: float) -> None:
        """Set a pad's brightness 0.0..1.0 via the brightness animation band."""
        self._send(p.ANIM_CHANNEL, self.pad_notes[pad],
                   p.brightness_velocity(level))

    # --- rate-limited grid flushing ----------------------------------------
    def queue_color(self, pad: int, velocity: int) -> None:
        """Queue a pad color to be sent on the next flush (delta-only)."""
        with self._lock:
            self._pending[pad] = velocity

    def flush(self, force: bool = False) -> int:
        """Send queued colors that changed, at most once per MIN_FLUSH_INTERVAL.

        Args:
            force: Bypass the rate limit (e.g. final frame).

        Returns:
            int: Number of pads actually written this flush.
        """
        now = time.monotonic()
        if not force and (now - self._last_flush) < MIN_FLUSH_INTERVAL:
            return 0
        with self._lock:
            changed = {
                pad: vel for pad, vel in self._pending.items()
                if self._last_color.get(pad) != vel
            }
            self._pending.clear()
        for pad, vel in changed.items():
            self._paint(pad, vel)
        self._last_flush = now
        return len(changed)

    # --- geometry helpers ---------------------------------------------------
    @staticmethod
    def xy_to_pad(x: int, y: int) -> int:
        """Convert (col, row) with 0,0 top-left to a 0..15 pad index."""
        return y * 4 + x

    @staticmethod
    def pad_to_xy(pad: int) -> tuple[int, int]:
        """Convert a 0..15 pad index to (col, row), 0,0 top-left."""
        return pad % 4, pad // 4
