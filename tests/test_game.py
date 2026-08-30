"""Offline tests for the rhythm-game core (beatmap generation + scoring).

Pure logic only — no pygame, no audio, no device. Song time is passed in
explicitly so every judgment is deterministic.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.beatmap import Beatmap, Note, generate_from_bpm, load_json, save_json  # noqa: E402
from game.engine import GOOD_WINDOW_MS, GameEngine, Judgement  # noqa: E402


# --- beatmap ----------------------------------------------------------------
def test_generate_is_reproducible_and_sorted():
    a = generate_from_bpm(seed=7)
    b = generate_from_bpm(seed=7)
    assert [ (n.time_ms, n.lane) for n in a.notes ] == \
           [ (n.time_ms, n.lane) for n in b.notes ]
    times = [n.time_ms for n in a.notes]
    assert times == sorted(times)
    assert all(0 <= n.lane < a.lanes for n in a.notes)
    assert len(a.notes) > 0


def test_generate_density_bounds():
    import pytest
    with pytest.raises(ValueError):
        generate_from_bpm(density=1.5)


def test_json_roundtrip(tmp_path):
    bm = generate_from_bpm(seed=3, bars=4)
    p = tmp_path / "chart.json"
    save_json(bm, str(p))
    loaded = load_json(str(p))
    assert loaded.title == bm.title and loaded.bpm == bm.bpm
    assert [(n.time_ms, n.lane) for n in loaded.notes] == \
           [(n.time_ms, n.lane) for n in bm.notes]


def _engine(notes):
    bm = Beatmap(title="t", bpm=120, lanes=4, notes=notes)
    return GameEngine(bm)


# --- judging ----------------------------------------------------------------
def test_perfect_hit_on_time():
    eng = _engine([Note(1000, 0)])
    res = eng.hit(lane=0, t_ms=1000)
    assert res is not None and res[1] is Judgement.PERFECT
    assert eng.combo == 1 and eng.score > 0


def test_great_and_good_windows():
    eng = _engine([Note(1000, 0), Note(2000, 1)])
    assert eng.hit(0, 1000 + 70)[1] is Judgement.GREAT      # 70ms off
    assert eng.hit(1, 2000 - 120)[1] is Judgement.GOOD      # 120ms off


def test_out_of_window_is_stray_no_note_consumed():
    eng = _engine([Note(1000, 0)])
    assert eng.hit(0, 1000 + GOOD_WINDOW_MS + 50) is None   # too late = stray
    # Note still unjudged, can still be hit in time.
    assert eng.hit(0, 1000)[1] is Judgement.PERFECT


def test_wrong_lane_does_not_hit():
    eng = _engine([Note(1000, 0)])
    assert eng.hit(1, 1000) is None


def test_nearest_note_chosen():
    eng = _engine([Note(1000, 0), Note(1080, 0)])
    st, _ = eng.hit(0, 1010)          # closer to 1000
    assert st.note.time_ms == 1000


def test_update_auto_misses_and_breaks_combo():
    eng = _engine([Note(1000, 0), Note(1500, 1)])
    eng.hit(0, 1000)                  # combo 1
    assert eng.combo == 1
    missed = eng.update(t_ms=1500 + GOOD_WINDOW_MS + 1)
    assert len(missed) == 1 and missed[0].judged is Judgement.MISS
    assert eng.combo == 0
    assert eng.counts[Judgement.MISS] == 1


def test_accuracy_and_finished():
    eng = _engine([Note(1000, 0), Note(2000, 1)])
    eng.hit(0, 1000)                  # perfect
    eng.hit(1, 2000)                  # perfect
    assert eng.accuracy == 1.0
    assert eng.finished(t_ms=2000)    # all judged
    assert eng.max_combo == 2


def test_upcoming_and_next_in_lane():
    notes = [Note(1000, 0), Note(1200, 2), Note(3000, 0)]
    eng = _engine(notes)
    up = eng.upcoming(t_ms=900, horizon_ms=500)
    assert {s.note.time_ms for s in up} == {1000, 1200}
    nxt = eng.next_in_lane(0, t_ms=900)
    assert nxt.note.time_ms == 1000
