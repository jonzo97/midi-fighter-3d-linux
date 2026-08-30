"""Beatmap data model + procedural generator + JSON persistence.

A beatmap is an ordered list of (time_ms, lane) notes plus tempo/metadata. The
generator lays notes on a BPM grid with a seeded, musical-ish pattern so the
demo song is reproducible without any asset files. Real songs load from JSON.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field

from . import LANES


@dataclass(frozen=True)
class Note:
    """A single target: hit ``lane`` at ``time_ms`` into the song."""
    time_ms: int
    lane: int


@dataclass
class Beatmap:
    """A playable chart.

    Attributes:
        title: Display name.
        bpm: Tempo in beats per minute.
        lanes: Number of lanes (columns).
        notes: Ordered Note list (ascending time).
        audio: Optional path to a backing track (None = generated metronome).
    """
    title: str
    bpm: float
    lanes: int
    notes: list[Note] = field(default_factory=list)
    audio: str | None = None

    @property
    def duration_ms(self) -> int:
        """End time of the chart (last note + 2s tail), 0 if empty."""
        return (self.notes[-1].time_ms + 2000) if self.notes else 0

    def beat_ms(self) -> float:
        """Milliseconds per beat."""
        return 60000.0 / self.bpm


def generate_from_bpm(
    title: str = "Demo Groove",
    bpm: float = 100.0,
    bars: int = 16,
    lanes: int = LANES,
    subdivisions: int = 2,
    density: float = 0.55,
    seed: int = 7,
) -> Beatmap:
    """Generate a reproducible demo beatmap on a BPM grid.

    Args:
        title: Chart name.
        bpm: Tempo.
        bars: Number of 4/4 bars.
        lanes: Lane count.
        subdivisions: Grid steps per beat (2 = eighth notes).
        density: Probability a grid step gets a note (0..1).
        seed: RNG seed for reproducibility.

    Returns:
        Beatmap: The generated chart.

    Raises:
        ValueError: If parameters are out of sensible ranges.
    """
    if not 0.0 <= density <= 1.0:
        raise ValueError("density must be in [0, 1]")
    if lanes < 1 or subdivisions < 1 or bars < 1:
        raise ValueError("lanes, subdivisions, bars must be >= 1")

    rng = random.Random(seed)
    beat = 60000.0 / bpm
    step = beat / subdivisions
    steps_per_bar = 4 * subdivisions
    notes: list[Note] = []
    lane_cycle = 0
    for s in range(bars * steps_per_bar):
        t = int(s * step)
        on_beat = (s % subdivisions) == 0
        # Downbeats are near-certain; offbeats gated by density for groove.
        if on_beat or rng.random() < density:
            # Alternate lanes with occasional jumps for interest.
            if rng.random() < 0.3:
                lane = rng.randrange(lanes)
            else:
                lane = lane_cycle % lanes
                lane_cycle += 1
            notes.append(Note(time_ms=t, lane=lane))
    notes.sort(key=lambda n: (n.time_ms, n.lane))
    return Beatmap(title=title, bpm=bpm, lanes=lanes, notes=notes)


def save_json(beatmap: Beatmap, path: str) -> None:
    """Write a beatmap to a JSON file."""
    data = asdict(beatmap)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)


def load_json(path: str) -> Beatmap:
    """Load a beatmap from a JSON file.

    Args:
        path: Path to the JSON chart.

    Returns:
        Beatmap: Parsed chart with Note objects.

    Raises:
        FileNotFoundError: If the file is missing.
        ValueError: If the JSON is malformed.
    """
    with open(path) as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"bad beatmap JSON: {exc}") from exc
    try:
        notes = [Note(time_ms=int(n["time_ms"]), lane=int(n["lane"]))
                 for n in data["notes"]]
        return Beatmap(
            title=data.get("title", "Untitled"),
            bpm=float(data["bpm"]),
            lanes=int(data.get("lanes", LANES)),
            notes=sorted(notes, key=lambda n: (n.time_ms, n.lane)),
            audio=data.get("audio"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid beatmap structure: {exc}") from exc
