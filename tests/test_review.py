"""Offline tests for the review bank, side keys, desk auto-switch and Tower mute.

unittest-style (runs under ``python -m unittest`` or pytest). No device, no real
keystrokes: the controller runs in dry-run mode and sway events are synthetic
JSON shaped like ``swaymsg -t subscribe`` output, with made-up titles only.
"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from midifighter import protocol as p  # noqa: E402
from midifighter.device import (  # noqa: E402
    BankButton, ButtonDown, SideButton, Tilt,
)
from macro.config import load_config  # noqa: E402
from macro.desks import DeskFollower, parse_line  # noqa: E402
from macro.engine import MacroController  # noqa: E402
from macro.leds import LayerLeds  # noqa: E402
from midifighter.sinks import LedSink  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "macro", "config.toml")

# The Tower's deck bank layout for the Midi Fighter, copied from
# command-center public/deck-pads.js FIGHTER_SLOTS @ fada6f4 ([row, col], row 0
# on top). The review bank must put the same verdict under the same finger.
TOWER_SLOTS = {
    "undo": [(0, 0)],
    "up": [(0, 1), (0, 2)],
    "left": [(1, 0), (2, 0)],
    "right": [(1, 3), (2, 3)],
    "down": [(3, 1), (3, 2)],
    "context": [(1, 1), (1, 2), (2, 1), (2, 2)],
}
# hyAway review page key for each Tower answer (context -> immersive view).
HYAWAY_KEY = {"undo": "z", "up": "Up", "left": "Left", "right": "Right",
              "down": "Down", "context": "t"}

# Synthetic marker title for the Tower and a stand-in for a private title.
TOWER_TITLE = "Sanguine Spire - Brave"
SECRET = "SECRET-TITLE-xyzzy"


def pad_at(row: int, col: int) -> int:
    """Pad index for a [row, col] with row 0 on top (pad 0 = note 36 = bottom-left)."""
    return (3 - row) * 4 + col


def press(pad: int) -> ButtonDown:
    return ButtonDown(pad=pad, note=36 + pad, velocity=127)


def make(log=None, leds=None):
    log = log if log is not None else []
    cfg = load_config(CONFIG)
    return MacroController(cfg, dry_run=True, on_fire=log.append, leds=leds), log


class NoNameDict(dict):
    """A sway container whose title must never be looked at."""

    def __getitem__(self, key):
        if key == "name":
            raise AssertionError("title of a private window was read")
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key == "name":
            raise AssertionError("title of a private window was read")
        return super().get(key, default)


def ws_event(num: int, change: str = "focus") -> dict:
    return {"change": change,
            "current": {"type": "workspace", "num": num, "name": str(num),
                        "nodes": []},
            "old": None}


def win_event(title: str, change: str = "focus", focused: bool = True,
              app_id: str = "brave-browser", guard: bool = False,
              con_id: int = 7) -> dict:
    cls = NoNameDict if guard else dict
    return {"change": change,
            "container": cls(id=con_id, type="con", app_id=app_id,
                             focused=focused, name=title)}


def on_desk(ws: list):
    """Fake window_public: the window sits on the focused desk ws[0]."""
    return lambda _con_id: ws[0] not in (9, 10)


class FakeSink(LedSink):
    def __init__(self):
        self.colors = {}
        self.writes = 0

    def set_color(self, pad, velocity):
        self.colors[pad] = velocity
        self.writes += 1

    def all_off(self):
        self.colors = {pad: p.COLOR_OFF for pad in range(16)}

    def flush(self, force=False):
        return 0


# ---------------------------------------------------------------------------
class TestBanks(unittest.TestCase):
    def test_helldivers_gone_and_bank4_is_review(self):
        cfg = load_config(CONFIG)
        self.assertNotIn("helldivers", cfg.layers)
        self.assertEqual(cfg.banks, ["sway", "window", "media", "review"])

    def test_review_pads_match_tower_deck_slots(self):
        ctl, _ = make()
        ctl.handle(BankButton(index=4))
        self.assertEqual(ctl.current, "review")
        for answer, cells in TOWER_SLOTS.items():
            for row, col in cells:
                res = ctl.handle(press(pad_at(row, col)))
                self.assertIsNotNone(res, f"{answer} at {row},{col} is empty")
                self.assertEqual(res.argv, ["wtype", "-k", HYAWAY_KEY[answer]],
                                 f"{answer} at {row},{col}")

    def test_review_tower_extras_corners_stay_dark(self):
        cfg = load_config(CONFIG)
        review = cfg.layers["review"]
        # Tower park (top right), depends (bottom left), more (bottom right).
        for row, col in [(0, 3), (3, 0), (3, 3)]:
            self.assertNotIn(pad_at(row, col), review.pads)

    def test_review_pad_colours_match_tower_tones(self):
        sink = FakeSink()
        leds = LayerLeds(sink)
        ctl, _ = make(leds=leds)
        ctl.handle(BankButton(index=4))
        want = {"right": "green", "left": "red", "up": "yellow",
                "down": "blue", "undo": "magenta", "context": "purple"}
        for answer, colour in want.items():
            for row, col in TOWER_SLOTS[answer]:
                self.assertEqual(sink.colors[pad_at(row, col)],
                                 p.color_velocity(colour, bright=False), answer)

    def test_review_has_no_tilt(self):
        ctl, _ = make()
        ctl.handle(BankButton(index=4))
        for edge in ("left", "right", "forward", "back"):
            self.assertIsNone(ctl.handle(Tilt(edge=edge, value=127)))


class TestSides(unittest.TestCase):
    def test_global_side_defaults_fire_on_every_layer(self):
        cfg = load_config(CONFIG)
        self.assertEqual(set(cfg.sides), {0, 1, 2, 3, 4, 5})
        for bank in (1, 2, 3):
            ctl, _ = make()
            ctl.handle(BankButton(index=bank))
            res = ctl.handle(SideButton(index=0))
            self.assertIsNotNone(res, f"bank {bank}")
            self.assertEqual(res.argv, ["sh", "-c", "playerctl play-pause"])

    def test_review_overrides_undo_and_immersive(self):
        ctl, _ = make()
        ctl.handle(BankButton(index=4))
        self.assertEqual(ctl.handle(SideButton(index=1)).argv, ["wtype", "-k", "z"])
        self.assertEqual(ctl.handle(SideButton(index=3)).argv, ["wtype", "-k", "t"])
        # Not overridden: the global play/pause still works on review.
        self.assertEqual(ctl.handle(SideButton(index=0)).argv,
                         ["sh", "-c", "playerctl play-pause"])

    def test_none_override_blocks_a_global(self):
        from macro.config import Config, Layer
        cfg = Config(start="a", banks=["a", "b"],
                     layers={"a": Layer(name="a"),
                             "b": Layer(name="b", sides={0: {"type": "none"}})},
                     sides={0: {"type": "notify", "text": "g"}})
        ctl = MacroController(cfg, dry_run=True)
        self.assertIsNotNone(ctl.handle(SideButton(index=0)))
        ctl.handle(BankButton(index=2))
        self.assertIsNone(ctl.handle(SideButton(index=0)))

    def test_previous_layer_side(self):
        ctl, _ = make()
        ctl.handle(BankButton(index=3))           # media
        ctl.handle(BankButton(index=4))           # review
        ctl.handle(SideButton(index=2))           # previous layer
        self.assertEqual(ctl.current, "media")
        ctl.handle(SideButton(index=2))
        self.assertEqual(ctl.current, "review")

    def test_bad_layer_target_is_rejected(self):
        import tempfile
        bad = ('[meta]\nbanks=["a"]\n[layers.a.pads]\n'
               '"0" = { type = "layer", to = "nowhere" }\n')
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as fh:
            fh.write(bad)
        try:
            with self.assertRaises(ValueError):
                load_config(fh.name)
        finally:
            os.unlink(fh.name)


class TestDeskFollow(unittest.TestCase):
    def setUp(self):
        self.log = []
        self.ctl, _ = make(log=self.log)
        self.ws = [3]
        self.follow = DeskFollower(self.ctl, self.ctl.config.auto,
                                   workspace_now=lambda: self.ws[0],
                                   window_public=on_desk(self.ws),
                                   log=self.log.append)
        self.follow.start(3)

    def goto(self, num):
        self.ws[0] = num
        self.follow.feed(ws_event(num))

    def test_auto_config_defaults(self):
        auto = self.ctl.config.auto
        self.assertTrue(auto.enabled)
        self.assertEqual(auto.review_layer, "review")
        self.assertEqual(set(auto.review_workspaces), {9, 10})
        self.assertIn("Sanguine Spire", auto.tower_markers)

    def test_private_desk_switches_to_review_and_back(self):
        self.ctl.handle(BankButton(index=3))
        self.goto(9)
        self.assertEqual(self.ctl.current, "review")
        self.goto(4)
        self.assertEqual(self.ctl.current, "media")

    def test_start_on_private_desk(self):
        ctl, _ = make()
        follow = DeskFollower(ctl, ctl.config.auto, workspace_now=lambda: 10,
                              window_public=on_desk([10]))
        follow.start(10)
        self.assertEqual(ctl.current, "review")
        follow.feed(ws_event(2))
        self.assertEqual(ctl.current, "sway")

    def test_manual_bank_wins_until_next_desk_change(self):
        self.goto(9)
        self.ctl.handle(BankButton(index=1))
        self.assertEqual(self.ctl.current, "sway")
        # Focus moves between windows on the same desk: manual choice stays.
        self.follow.feed(win_event(SECRET, guard=True))
        self.follow.feed(ws_event(9))                 # re-focus same desk
        self.assertEqual(self.ctl.current, "sway")
        # Next desk change (9 -> 10) re-applies review.
        self.goto(10)
        self.assertEqual(self.ctl.current, "review")
        # Leaving restores the layer from before the private desks.
        self.goto(1)
        self.assertEqual(self.ctl.current, "sway")

    def test_ordinary_desk_changes_leave_the_layer_alone(self):
        self.ctl.handle(BankButton(index=2))
        self.goto(4)
        self.goto(5)
        self.assertEqual(self.ctl.current, "window")

    def test_private_titles_never_read(self):
        self.goto(9)
        # Focus and title events from windows on 9/10 must not touch "name".
        self.follow.feed(win_event(SECRET, guard=True))
        self.follow.feed(win_event(SECRET, change="title", guard=True))
        self.goto(10)
        self.follow.feed(win_event(SECRET, guard=True,
                                   app_id="brave-abc-Default"))

    def test_window_focus_checks_desk_before_title(self):
        # A window focus event that arrives before its workspace event still
        # never reads a private title: the desk is asked first.
        self.ws[0] = 10
        self.follow.feed(win_event(SECRET, guard=True))
        self.assertEqual(self.ctl.current, "review")

    def test_unfocused_title_changes_ignored(self):
        self.follow.feed(win_event(SECRET, change="title", focused=False,
                                   guard=True))
        self.assertFalse(self.ctl.muted)

    def test_logs_hold_no_titles(self):
        self.follow.feed(win_event(TOWER_TITLE))
        self.ctl.handle(press(0))
        self.follow.feed(win_event("Some Other Page - Brave"))
        self.goto(9)
        self.ctl.handle(press(13))
        self.goto(2)
        blob = json.dumps(self.log)
        for word in ("Sanguine", "Spire", "Other Page", "Brave", "brave"):
            self.assertNotIn(word, blob)
        self.assertTrue(any("review" in line for line in self.log))

    def test_parse_line(self):
        self.assertEqual(parse_line(json.dumps(ws_event(9)))["current"]["num"], 9)
        self.assertIsNone(parse_line("not json"))
        self.assertIsNone(parse_line("[1, 2]"))
        self.assertIsNone(parse_line(""))


class TestTowerMute(unittest.TestCase):
    def setUp(self):
        self.log = []
        self.sink = FakeSink()
        self.ctl, _ = make(log=self.log, leds=LayerLeds(self.sink))
        self.ctl.start_leds()
        self.ws = [2]
        self.follow = DeskFollower(self.ctl, self.ctl.config.auto,
                                   workspace_now=lambda: self.ws[0],
                                   window_public=on_desk(self.ws),
                                   log=self.log.append)
        self.follow.start(2)
        self.follow.feed(win_event(TOWER_TITLE))

    def test_tower_focus_drops_pads_sides_tilt(self):
        self.assertTrue(self.ctl.muted)
        self.assertIsNone(self.ctl.handle(press(0)))
        self.assertIsNone(self.ctl.handle(SideButton(index=0)))
        self.assertIsNone(self.ctl.handle(Tilt(edge="forward", value=127)))

    def test_bank_switch_tracked_while_muted_without_leds(self):
        writes = self.sink.writes
        self.ctl.handle(BankButton(index=4))
        self.assertEqual(self.ctl.current, "review")
        self.assertEqual(self.sink.writes, writes, "LEDs belong to the Tower")
        # Focus leaves the Tower: actions and LEDs come back on the new layer.
        self.follow.feed(win_event("A terminal", app_id="kitty"))
        self.assertFalse(self.ctl.muted)
        self.assertGreater(self.sink.writes, writes)
        self.assertEqual(self.ctl.handle(press(pad_at(1, 3))).argv,
                         ["wtype", "-k", "Right"])

    def test_tab_switch_to_tower_mutes_via_title_event(self):
        self.follow.feed(win_event("Docs - Brave"))
        self.assertFalse(self.ctl.muted)
        self.follow.feed(win_event(TOWER_TITLE, change="title"))
        self.assertTrue(self.ctl.muted)

    def test_desk_change_unmutes(self):
        self.ws[0] = 3
        self.follow.feed(ws_event(3))
        self.assertFalse(self.ctl.muted)

    def test_tower_marker_on_private_desk_is_ignored(self):
        self.ws[0] = 9
        self.follow.feed(ws_event(9))
        self.follow.feed(win_event(TOWER_TITLE, guard=True))
        self.assertFalse(self.ctl.muted)

    def test_marker_is_configurable(self):
        ctl, _ = make()
        ctl.config.auto.tower_markers = ("My Tower",)
        follow = DeskFollower(ctl, ctl.config.auto, workspace_now=lambda: 1,
                              window_public=on_desk([1]))
        follow.start(1)
        follow.feed(win_event(TOWER_TITLE))
        self.assertFalse(ctl.muted)
        follow.feed(win_event("my tower - Brave"))
        self.assertTrue(ctl.muted)

    def test_title_gate_uses_the_windows_own_desk(self):
        # Review finding f6760985: focus left 9/10 before the desk query, but
        # the event's window is still on desk 9. Its title must not be read.
        self.follow.feed(win_event("A terminal", app_id="kitty"))
        self.ws[0] = 3
        follow = DeskFollower(self.ctl, self.ctl.config.auto,
                              workspace_now=lambda: 3,
                              window_public=lambda con_id: False)
        follow.start(3)
        follow.feed(win_event(SECRET, guard=True, con_id=42))
        follow.feed(win_event(SECRET, change="title", guard=True, con_id=42))
        self.assertFalse(self.ctl.muted)

    def test_unconfirmed_window_title_is_not_read(self):
        # A failed or empty desk query (window closed, sway busy) reads nothing.
        follow = DeskFollower(self.ctl, self.ctl.config.auto,
                              workspace_now=lambda: 2,
                              window_public=lambda con_id: None)
        follow.start(2)
        follow.feed(win_event(SECRET, guard=True, con_id=43))
        self.assertFalse(self.ctl.muted)

    def test_window_public_gets_the_events_con_id(self):
        asked = []
        follow = DeskFollower(self.ctl, self.ctl.config.auto,
                              workspace_now=lambda: 2,
                              window_public=lambda con_id: asked.append(con_id) or True)
        follow.start(2)
        follow.feed(win_event(TOWER_TITLE, con_id=99))
        self.assertEqual(asked, [99])
        self.assertTrue(self.ctl.muted)

    def test_desk_query_regex_by_number(self):
        from macro.desks import public_desk_regex
        import re
        rx = re.compile(public_desk_regex((9, 10)))
        for name in ("1", "3", "90", "11", "2:web", "notes"):
            self.assertTrue(rx.search(name), name)
        for name in ("9", "10", "9:media", "10 private"):
            self.assertFalse(rx.search(name), name)

    def test_tilt_does_not_fire_on_unmute_from_a_held_tilt(self):
        self.ctl.handle(Tilt(edge="forward", value=127))      # muted, held
        self.follow.feed(win_event("A terminal", app_id="kitty"))
        self.assertIsNone(self.ctl.handle(Tilt(edge="forward", value=127)))




if __name__ == "__main__":
    unittest.main()
