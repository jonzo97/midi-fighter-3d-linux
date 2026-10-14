"""MacroController — routes Midi Fighter 3D events to configured actions.

Wiring:
    ButtonDown(pad)   -> current layer's pad action
    BankButton(n)     -> switch to the layer at banks[n-1]
    SideButton(i)     -> current layer's side override, else the [sides] default
    Tilt(edge, value) -> current layer's tilt action, edge-debounced so a single
                         physical tilt fires once (the device streams CC values)

Two inputs come from outside the device (macro/desks.py, the sway follower):
    set_layer(name)   -> switch layer (a desk change)
    set_muted(flag)   -> while the Tower page is focused, pads, sides and tilt
                         do nothing (the Tower's Web MIDI owns them) and the
                         LEDs are left to the Tower; bank buttons still switch.

Actions run via macro.actions.run_action; pass dry_run=True to preview without
executing (safe for testing against a live Sway session). ``type = "layer"``
actions (``to`` = a layer, "previous" or "show") are handled here.

The MIDI input thread and the sway thread both call in, so every entry point
holds one re-entrant lock.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from .actions import ActionResult, run_action
from .config import LAYER_ACTION, Config


class MacroController:
    """Stateful dispatcher from decoded device events to actions.

    Args:
        config: Parsed macro Config.
        dry_run: If True, actions are previewed, not executed.
        on_fire: Optional callback(str) for human-readable activity logging.
        tilt_high: Override the config's tilt activation threshold.
        tilt_low: Override the config's tilt re-arm threshold.
        leds: Optional LayerLeds for LED feedback.
    """

    def __init__(
        self,
        config: Config,
        dry_run: bool = False,
        on_fire: Optional[Callable[[str], None]] = None,
        tilt_high: Optional[int] = None,
        tilt_low: Optional[int] = None,
        leds=None,
    ) -> None:
        self.config = config
        self.dry_run = dry_run
        self.on_fire = on_fire or (lambda _s: None)
        self.current = config.start
        self.previous = config.start   # layer before the last switch
        self.muted = False             # True while the Tower page has focus
        self.leds = leds          # optional LayerLeds for LED feedback
        # Tilt fires when a CC value rises past tilt_high, re-arms below tilt_low.
        self.tilt_high = tilt_high if tilt_high is not None else config.tilt_high
        self.tilt_low = tilt_low if tilt_low is not None else config.tilt_low
        self._tilt_armed = {"left": True, "forward": True, "right": True, "back": True}
        self._lock = threading.RLock()

    def start_leds(self) -> None:
        """Paint the initial layer's LED feedback (call after the device opens)."""
        with self._lock:
            if self.leds is not None and not self.muted:
                self.leds.on_layer(self._layer())

    # --- event entry point --------------------------------------------------
    def handle(self, ev) -> Optional[ActionResult]:
        """Dispatch one decoded event. Returns the ActionResult if one ran."""
        # Imported lazily to avoid a hard dependency at module import time.
        from midifighter.device import (
            BankButton, ButtonDown, SideButton, Tilt,
        )

        with self._lock:
            if isinstance(ev, BankButton):
                idx = ev.index - 1
                if 0 <= idx < len(self.config.banks):
                    self.set_layer(self.config.banks[idx], why="bank")
                return None
            if isinstance(ev, Tilt):
                return self._handle_tilt(ev.edge, ev.value)
            if self.muted:
                return None
            if isinstance(ev, ButtonDown):
                spec = self._layer().pads.get(ev.pad)
                res = self._fire(spec, f"pad {ev.pad}")
                if self.leds is not None and spec:
                    self.leds.on_fire(ev.pad)
                return res
            if isinstance(ev, SideButton):
                return self._fire(self.config.side_action(self.current, ev.index),
                                  f"side {ev.index}")
            return None

    # --- outside inputs (desk follower) -------------------------------------
    def set_layer(self, name: str, why: str = "") -> bool:
        """Make ``name`` the active layer.

        Args:
            name: A layer defined in the config.
            why: Short reason for the log line ("bank", "desk 9", ...).

        Returns:
            bool: True if the layer exists (switched or already active).
        """
        with self._lock:
            if name not in self.config.layers:
                return False
            if name != self.current:
                self.previous, self.current = self.current, name
            self.on_fire(f"[layer] -> {self.current}" + (f" ({why})" if why else ""))
            if self.leds is not None and not self.muted:
                self.leds.on_layer(self._layer())
            return True

    def set_muted(self, muted: bool) -> None:
        """Mute or unmute pad/side/tilt actions (the Tower has focus).

        Unmuting repaints the active layer's LEDs, which the Tower may have
        changed while it owned the device.
        """
        with self._lock:
            muted = bool(muted)
            if muted == self.muted:
                return
            self.muted = muted
            self.on_fire("[tower] focused: pads muted" if muted
                         else "[tower] left: pads live")
            if not muted and self.leds is not None:
                self.leds.on_layer(self._layer())

    # --- helpers ------------------------------------------------------------
    def _layer(self):
        return self.config.layers[self.current]

    def _handle_tilt(self, edge: str, value: int) -> Optional[ActionResult]:
        if value >= self.tilt_high and self._tilt_armed.get(edge, True):
            # Disarm even when muted, so a tilt held through an unmute does
            # not fire the moment the Tower loses focus.
            self._tilt_armed[edge] = False
            if self.muted:
                return None
            return self._fire(self._layer().tilt.get(edge), f"tilt {edge}")
        if value <= self.tilt_low:
            self._tilt_armed[edge] = True
        return None

    def _fire(self, spec: Optional[dict], label: str) -> Optional[ActionResult]:
        if not spec:
            return None
        if spec.get("type") == LAYER_ACTION:
            return self._layer_action(spec, label)
        result = run_action(spec, dry_run=self.dry_run)
        tag = "would run" if self.dry_run else ("ran" if result.ok else "FAIL")
        self.on_fire(f"[{self.current}] {label}: {tag} {' '.join(result.argv)}"
                     + (f" ({result.detail})" if result.detail and not result.ok
                        else ""))
        return result

    def _layer_action(self, spec: dict, label: str) -> ActionResult:
        """Run an internal ``type = "layer"`` action."""
        target = spec.get("to")
        if target == "show":
            bank = (self.config.banks.index(self.current) + 1
                    if self.current in self.config.banks else 0)
            text = f"Layer: {self.current}" + (f" (bank {bank})" if bank else "")
            return self._fire({"type": "notify", "text": text}, label)
        name = self.previous if target == "previous" else target
        ok = self.set_layer(name, why=label)
        return ActionResult(ok=ok, argv=["layer", str(name)],
                            detail="" if ok else f"no layer {name!r}")
