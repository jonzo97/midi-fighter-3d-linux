"""Rhythm-game scoring + timing core — no pygame, no MIDI, no wall clock.

Everything here is driven by an explicit song time in milliseconds, so the whole
judgment/scoring model is deterministic and unit-testable. The render loop and
input thread feed it time and hits; it returns judgments and exposes state for
drawing and LED cues.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .beatmap import Beatmap, Note


class Judgement(str, Enum):
    """Hit quality, best to worst."""
    PERFECT = "perfect"
    GREAT = "great"
    GOOD = "good"
    MISS = "miss"


# Absolute timing error (ms) upper bounds per judgment; GOOD == the hit window.
_WINDOWS = ((Judgement.PERFECT, 45), (Judgement.GREAT, 90), (Judgement.GOOD, 135))
GOOD_WINDOW_MS = 135
_SCORE = {Judgement.PERFECT: 300, Judgement.GREAT: 200,
          Judgement.GOOD: 100, Judgement.MISS: 0}
_ACCURACY_WEIGHT = {Judgement.PERFECT: 1.0, Judgement.GREAT: 0.66,
                    Judgement.GOOD: 0.33, Judgement.MISS: 0.0}


@dataclass
class NoteState:
    """A beatmap note plus its live judgment state."""
    note: Note
    judged: Optional[Judgement] = None
    hit_dt: Optional[int] = None      # signed ms error (+late, -early)


class GameEngine:
    """Judges hits against a beatmap and tracks score/combo/accuracy.

    Args:
        beatmap: The chart to play.
        good_window_ms: Outer hit window; beyond it a hit misses the note and a
            note passing this far past its time auto-misses.
    """

    def __init__(self, beatmap: Beatmap, good_window_ms: int = GOOD_WINDOW_MS) -> None:
        self.beatmap = beatmap
        self.good_window = good_window_ms
        self._states = [NoteState(n) for n in beatmap.notes]
        self._by_lane: dict[int, list[NoteState]] = {}
        for st in self._states:
            self._by_lane.setdefault(st.note.lane, []).append(st)
        self.score = 0
        self.combo = 0
        self.max_combo = 0
        self.counts = {j: 0 for j in Judgement}

    # --- input --------------------------------------------------------------
    def hit(self, lane: int, t_ms: int) -> Optional[tuple[NoteState, Judgement]]:
        """Register a pad hit in ``lane`` at song time ``t_ms``.

        Judges the nearest unjudged note in that lane within the hit window.

        Args:
            lane: Lane index (0-based).
            t_ms: Song time of the hit.

        Returns:
            (NoteState, Judgement) if a note was judged, else None (stray hit).
        """
        best: Optional[NoteState] = None
        best_dt = 0
        for st in self._by_lane.get(lane, ()):
            if st.judged is not None:
                continue
            dt = t_ms - st.note.time_ms
            if abs(dt) <= self.good_window and (best is None or abs(dt) < abs(best_dt)):
                best, best_dt = st, dt
        if best is None:
            return None
        judgement = self._judge(abs(best_dt))
        best.judged = judgement
        best.hit_dt = best_dt
        self._apply(judgement)
        return best, judgement

    def update(self, t_ms: int) -> list[NoteState]:
        """Auto-miss notes that have passed the hit window unjudged.

        Args:
            t_ms: Current song time.

        Returns:
            list[NoteState]: Notes newly marked MISS this tick.
        """
        newly: list[NoteState] = []
        for st in self._states:
            if st.judged is None and (t_ms - st.note.time_ms) > self.good_window:
                st.judged = Judgement.MISS
                self._apply(Judgement.MISS)
                newly.append(st)
        return newly

    # --- queries for render / LEDs -----------------------------------------
    def upcoming(self, t_ms: int, horizon_ms: int) -> list[NoteState]:
        """Unjudged notes with target time in [t_ms - window, t_ms + horizon]."""
        lo = t_ms - self.good_window
        hi = t_ms + horizon_ms
        return [st for st in self._states
                if st.judged is None and lo <= st.note.time_ms <= hi]

    def next_in_lane(self, lane: int, t_ms: int) -> Optional[NoteState]:
        """The soonest unjudged note in a lane at/after (t_ms - window)."""
        best: Optional[NoteState] = None
        for st in self._by_lane.get(lane, ()):
            if st.judged is None and st.note.time_ms >= t_ms - self.good_window:
                if best is None or st.note.time_ms < best.note.time_ms:
                    best = st
        return best

    def finished(self, t_ms: int) -> bool:
        """True once every note is judged or the song has fully elapsed."""
        if t_ms >= self.beatmap.duration_ms:
            return True
        return all(st.judged is not None for st in self._states)

    @property
    def total_notes(self) -> int:
        return len(self._states)

    @property
    def accuracy(self) -> float:
        """Weighted accuracy 0..1 over judged notes (1.0 if none judged yet)."""
        judged = sum(self.counts.values())
        if judged == 0:
            return 1.0
        earned = sum(_ACCURACY_WEIGHT[j] * n for j, n in self.counts.items())
        return earned / judged

    # --- internals ----------------------------------------------------------
    def _judge(self, abs_dt: int) -> Judgement:
        for judgement, window in _WINDOWS:
            if abs_dt <= window:
                return judgement
        return Judgement.GOOD

    def _apply(self, judgement: Judgement) -> None:
        self.counts[judgement] += 1
        if judgement is Judgement.MISS:
            self.combo = 0
        else:
            self.combo += 1
            self.max_combo = max(self.max_combo, self.combo)
            # Small combo bonus rewards streaks without runaway scaling.
            self.score += _SCORE[judgement] + min(self.combo, 50)
