"""Procedural audio for the rhythm game — no asset files required.

Synthesizes a metronome click, a per-lane hit tone, and a miss thud with numpy
and plays them through pygame.mixer. Degrades gracefully to silent if no audio
device is available (the game stays fully playable, just muted).
"""

from __future__ import annotations

import numpy as np

_SR = 44100
# Pleasant-ish per-lane pitches (E4, G4, B4, D5).
_LANE_FREQS = (330.0, 392.0, 494.0, 587.0)


def _make_sound(freq: float, ms: int, vol: float = 0.4, decay: float = 8.0):
    """Build a decaying sine Sound. Import pygame lazily (mixer must be up)."""
    import pygame
    n = max(1, int(_SR * ms / 1000))
    t = np.arange(n) / _SR
    wave = np.sin(2 * np.pi * freq * t) * np.exp(-t * decay)
    samples = (wave * vol * 32767).astype(np.int16)
    stereo = np.ascontiguousarray(np.column_stack([samples, samples]))
    return pygame.sndarray.make_sound(stereo)


class GameAudio:
    """Loads/plays the game's procedural sounds.

    Args:
        enabled: If False, all playback is a no-op (silent mode).
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._click = None
        self._hits: list = []
        self._miss = None
        if not enabled:
            return
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=_SR, size=-16, channels=2, buffer=512)
            self._click = _make_sound(1200, 40, vol=0.25, decay=25.0)
            self._hits = [_make_sound(f, 120, vol=0.5) for f in _LANE_FREQS]
            self._miss = _make_sound(110, 160, vol=0.4, decay=6.0)
        except Exception as exc:   # noqa: BLE001 — audio is optional, never fatal
            print(f"[warn] audio disabled: {exc}")
            self.enabled = False

    def click(self) -> None:
        """Play the metronome click."""
        if self.enabled and self._click:
            self._click.play()

    def hit(self, lane: int) -> None:
        """Play the tone for a hit in ``lane``."""
        if self.enabled and self._hits:
            self._hits[lane % len(self._hits)].play()

    def miss(self) -> None:
        """Play the miss thud."""
        if self.enabled and self._miss:
            self._miss.play()
