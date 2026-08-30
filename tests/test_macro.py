"""Offline tests for the macro controller (no device, no real actions).

Actions run in dry-run mode so nothing touches the live Sway session.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from midifighter.device import (  # noqa: E402
    BankButton, ButtonDown, SideButton, Tilt,
)
from macro.actions import _build_argv, run_action  # noqa: E402
from macro.config import load_config  # noqa: E402
from macro.engine import MacroController  # noqa: E402

CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "macro", "config.toml")


# --- config -----------------------------------------------------------------
def test_load_sample_config():
    cfg = load_config(CONFIG)
    assert cfg.start == "sway"
    assert cfg.banks == ["sway", "window", "media", "helldivers"]
    assert set(cfg.layers) == {"sway", "window", "media", "helldivers"}
    # pad 0 on sway switches to workspace 1
    assert cfg.layers["sway"].pads[0]["cmd"] == "workspace number 1"
    assert cfg.layers["sway"].tilt["forward"]["cmd"] == "workspace next"


# --- action argv building ---------------------------------------------------
def test_build_sway():
    assert _build_argv({"type": "sway", "cmd": "workspace number 1"}) == \
        ["swaymsg", "workspace", "number", "1"]


def test_build_key_with_mods():
    argv = _build_argv({"type": "key", "mods": ["ctrl", "shift"], "key": "Left"})
    assert argv == ["wtype", "-M", "ctrl", "-M", "shift", "-k", "Left",
                    "-m", "shift", "-m", "ctrl"]


def test_build_text_notify_shell():
    assert _build_argv({"type": "text", "text": "gg"}) == ["wtype", "gg"]
    assert _build_argv({"type": "shell", "cmd": "ls"}) == ["sh", "-c", "ls"]
    n = _build_argv({"type": "notify", "text": "hi"})
    assert n[0] == "notify-send" and n[-1] == "hi"


def test_build_unknown_type_raises():
    import pytest
    with pytest.raises(ValueError):
        _build_argv({"type": "bogus"})


def test_run_action_dry_run_never_executes():
    res = run_action({"type": "sway", "cmd": "workspace number 1"}, dry_run=True)
    assert res.ok and res.argv[0] == "swaymsg" and res.detail == "dry-run"


# --- controller dispatch ----------------------------------------------------
def _controller():
    log = []
    cfg = load_config(CONFIG)
    ctl = MacroController(cfg, dry_run=True, on_fire=log.append)
    return ctl, log


def test_pad_press_fires_layer_action():
    ctl, log = _controller()
    res = ctl.handle(ButtonDown(pad=0, note=36, velocity=127))
    assert res is not None and res.ok
    assert res.argv == ["swaymsg", "workspace", "number", "1"]


def test_bank_button_switches_layer():
    ctl, log = _controller()
    assert ctl.current == "sway"
    ctl.handle(BankButton(index=2))
    assert ctl.current == "window"
    # Now pad 0 fires the window layer's action.
    res = ctl.handle(ButtonDown(pad=0, note=36, velocity=127))
    assert res.argv == ["swaymsg", "move", "container", "to", "workspace",
                        "number", "1"]


def test_side_button_action():
    ctl, log = _controller()
    res = ctl.handle(SideButton(index=0))
    assert res is not None and res.argv[0] == "notify-send"


def test_tilt_debounce_fires_once():
    ctl, log = _controller()
    hi, lo = ctl.tilt_high, ctl.tilt_low
    # Rising past high fires once.
    r1 = ctl.handle(Tilt(edge="forward", value=hi + 5))
    assert r1 is not None and r1.argv == ["swaymsg", "workspace", "next"]
    # Still held high -> no re-fire.
    r2 = ctl.handle(Tilt(edge="forward", value=hi + 5))
    assert r2 is None
    # Drop below low re-arms, then a new tilt fires again.
    ctl.handle(Tilt(edge="forward", value=lo - 5))
    r3 = ctl.handle(Tilt(edge="forward", value=hi + 5))
    assert r3 is not None


def test_config_tilt_thresholds_loaded():
    ctl, _ = _controller()
    # Sample config sets lighter defaults than the old hardcoded 100/40.
    assert ctl.tilt_high == 45 and ctl.tilt_low == 18


def test_tilt_threshold_override():
    from macro.config import load_config
    cfg = load_config(CONFIG)
    ctl = MacroController(cfg, dry_run=True, tilt_high=30, tilt_low=10)
    assert ctl.tilt_high == 30
    # A tilt of 32 now fires (would not at the old threshold of 100).
    assert ctl.handle(Tilt(edge="forward", value=32)) is not None


def test_unmapped_pad_is_noop():
    ctl, log = _controller()
    # Pad 9 is unmapped on the sway layer.
    assert ctl.handle(ButtonDown(pad=9, note=45, velocity=127)) is None
