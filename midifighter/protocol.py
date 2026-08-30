"""Midi Fighter 3D wire protocol constants.

Values are marked VERIFIED (measured on this hardware or accepted by the
device), GUIDE (from the official User Guide v1.03 — authoritative but not yet
visually confirmed on our unit), or PENDING (must be captured live in Phase 1).

Channel note: MIDI channels are conventionally 1-indexed (ch 1..16) but the
python-rtmidi / mido API uses 0-indexed channel numbers. Constants here store
the 1-indexed MIDI channel; use ``to_mido(ch)`` when building mido Messages.

References:
    User Guide v1.03 color table (Fig 2), animation bands, motion CCs.
    Local probes: amidi write of "92 3C 0D"; smoke_test received CC1 on ch 4.
"""

from __future__ import annotations

import json
import os

# --- Channels ---------------------------------------------------------------
# GUIDE: base channel factory default = 3, using 3 consecutive channels.
# VERIFIED (input): a Forward-tilt CC1 arrived on MIDI ch 4 during smoke_test,
# which is base+1 — consistent with base channel = 3.
BASE_CHANNEL = 3          # GUIDE + consistent with observed motion channel
COLOR_CHANNEL = 3         # base: pad color set here (GUIDE; note 60 write accepted)
ANIM_CHANNEL = 4          # base+1: brightness/gate/pulse (GUIDE)
INPUT_CHANNEL = 3         # base: pad Note-On/Off on press (GUIDE; PENDING confirm)
MOTION_CHANNEL = 4        # base+1: tilt CCs + bank changes (VERIFIED for CC1)


def to_mido(midi_channel: int) -> int:
    """Convert a 1-indexed MIDI channel to a 0-indexed mido channel.

    Args:
        midi_channel: MIDI channel in the human 1..16 range.

    Returns:
        int: 0-indexed channel (0..15) for mido.Message(channel=...).
    """
    return midi_channel - 1


# --- Color palette ----------------------------------------------------------
# GUIDE Fig 2: 10 hues x {bright, dim}, selected by Note-On velocity on the
# color channel. Velocity 0 releases the MIDI LED override. 121-127 forces the
# Utility-configured active color (avoid for normal animation).
# Map: name -> (bright_velocity, dim_velocity).
COLORS: dict[str, tuple[int, int]] = {
    "red":     (13, 19),
    "orange":  (25, 31),
    "yellow":  (37, 43),
    "lime":    (49, 55),
    "green":   (61, 67),
    "cyan":    (73, 79),
    "blue":    (85, 91),
    "purple":  (97, 103),
    "magenta": (109, 115),
    "white":   (121, 5),   # dim-white band is 0-12; 5 is a safe mid value
}
COLOR_OFF = 0             # release LED override

# Ordered hue list for rainbow/sweep effects (excludes white).
HUE_ORDER = ["red", "orange", "yellow", "lime", "green",
             "cyan", "blue", "purple", "magenta"]


def color_velocity(name: str, bright: bool = True) -> int:
    """Return the Note-On velocity that selects a palette color.

    Args:
        name: Color name from COLORS.
        bright: True for the bright band, False for dim.

    Returns:
        int: Velocity 0..127.

    Raises:
        KeyError: If name is not a known color.
    """
    b, d = COLORS[name]
    return b if bright else d


# Approximate sRGB for each palette color, for terminal / pygame rendering.
COLOR_RGB: dict[str, tuple[int, int, int]] = {
    "red":     (220, 40, 40),
    "orange":  (230, 120, 20),
    "yellow":  (230, 220, 40),
    "lime":    (150, 220, 40),
    "green":   (40, 200, 60),
    "cyan":    (40, 210, 210),
    "blue":    (60, 90, 235),
    "purple":  (150, 60, 220),
    "magenta": (220, 60, 180),
    "white":   (235, 235, 235),
}


def velocity_to_color(velocity: int) -> tuple[str | None, bool]:
    """Reverse the color table: map a color-channel velocity to (name, bright).

    The palette occupies velocities 13..120 as 18 contiguous 6-wide bands
    (9 hues x bright/dim), with white at the 0-12 (dim) and 121-127 (bright)
    edges. Velocity 0 is "off" (no MIDI color override).

    Args:
        velocity: Color-channel Note-On velocity, 0..127.

    Returns:
        tuple[str | None, bool]: (color name, is_bright). Name is None when the
        velocity means "off".
    """
    v = max(0, min(127, velocity))
    if v == 0:
        return None, False
    if v <= 12:
        return "white", False
    if v >= 121:
        return "white", True
    band = (v - 13) // 6          # 0..17
    hue = HUE_ORDER[band // 2]    # 9 hues
    is_bright = (band % 2) == 0
    return hue, is_bright


# --- Animation bands (sent on ANIM_CHANNEL) ---------------------------------
# GUIDE: velocity band selects the animation. Brightness gives 16 levels for
# VU-meter effects; gate/pulse give 8 rates each.
BRIGHTNESS_MIN_VEL = 18   # 0% .. maps up to
BRIGHTNESS_MAX_VEL = 33   # ..100% across 16 steps
GATE_MIN_VEL = 34         # 8 flash rates (34..41)
GATE_MAX_VEL = 41
PULSE_MIN_VEL = 42        # 8 pulse rates (42..49)
PULSE_MAX_VEL = 49
ANIM_OFF = 0


def brightness_velocity(level: float) -> int:
    """Map a 0.0..1.0 brightness to its animation velocity (16 steps).

    Args:
        level: Brightness fraction, clamped to [0, 1].

    Returns:
        int: Velocity in [BRIGHTNESS_MIN_VEL, BRIGHTNESS_MAX_VEL].
    """
    level = max(0.0, min(1.0, level))
    span = BRIGHTNESS_MAX_VEL - BRIGHTNESS_MIN_VEL
    return BRIGHTNESS_MIN_VEL + round(level * span)


# --- Motion (GUIDE; CC1 VERIFIED) -------------------------------------------
# Edge tilt CCs on MOTION_CHANNEL, value 0..127.
TILT_LEFT_CC = 0
TILT_FORWARD_CC = 1       # VERIFIED: observed in smoke_test
TILT_RIGHT_CC = 2
TILT_BACK_CC = 3

# --- Bank change notes (GUIDE, on MOTION_CHANNEL) ---------------------------
# 4-Banks Mode (factory default) remaps pads per bank and, per the guide,
# blocks LED control over MIDI. May need disabling via the Midi Fighter Utility.
BANK_NOTES = {1: 0, 2: 1, 3: 2, 4: 3}  # C-1..D#-1

# --- Pad note map -----------------------------------------------------------
# VERIFIED via tools/capture_input.py (928 events): the 16 arcade pads send
# Note-On on MIDI ch 3, notes 36..51 (top-left..bottom-right). The candidate
# guess was exactly right.
PAD_NOTES_VERIFIED = True
PAD_NOTES: list[int] = list(range(36, 52))  # VERIFIED: 16 notes, ch 3

# VERIFIED: side buttons and bank buttons live on MOTION_CHANNEL (ch 4).
SIDE_BUTTON_NOTES = [38, 39, 40, 41, 42, 43]   # 6 side buttons, ch 4
# VERIFIED: per-pad rotation sends CC (pad note number) on MOTION_CHANNEL.
# i.e. rotating the pad with note N emits control_change ch4 control=N.
ROTATION_CC_FOR_NOTE = {n: n for n in PAD_NOTES}  # ch 4, CC 36..51

_CAPTURE_LOG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tools", "capture_log.json",
)


def load_captured_pad_notes(path: str = _CAPTURE_LOG) -> list[int] | None:
    """Load verified pad notes from a capture_input.py log, if present.

    Reads the note-on notes seen on INPUT_CHANNEL and returns them sorted. This
    upgrades PAD_NOTES from the unverified candidate to measured truth.

    Args:
        path: Path to capture_log.json.

    Returns:
        list[int] | None: Sorted distinct pad notes, or None if no usable log.
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    ch0 = to_mido(INPUT_CHANNEL)
    notes = {
        e["note"]
        for e in data.get("events", [])
        if e.get("type") == "note_on"
        and e.get("velocity", 0) > 0
        and e.get("channel") == ch0
    }
    return sorted(notes) if notes else None
