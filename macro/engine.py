"""MacroController — routes Midi Fighter 3D events to configured actions.

Wiring:
    ButtonDown(pad)   -> current layer's pad action
    BankButton(n)     -> switch to the layer at banks[n-1]
    SideButton(i)     -> current layer's side action
    Tilt(edge, value) -> current layer's tilt action, edge-debounced so a single
                         physical tilt fires once (the device streams CC values)

Actions run via macro.actions.run_action; pass dry_run=True to preview without
executing (safe for testing against a live Sway session).
"""

from __future__ import annotations

from typing import Callable, Optional

from .actions import ActionResult, run_action
from .config import Config


class MacroController:
    """Stateful dispatcher from decoded device events to actions.

    Args:
        config: Parsed macro Config.
        dry_run: If True, actions are previewed, not executed.
        on_fire: Optional callback(str) for human-readable activity logging.
        tilt_high: Override the config's tilt activation threshold.
        tilt_low: Override the config's tilt re-arm threshold.
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
        self.leds = leds          # optional LayerLeds for LED feedback
        # Tilt fires when a CC value rises past tilt_high, re-arms below tilt_low.
        self.tilt_high = tilt_high if tilt_high is not None else config.tilt_high
        self.tilt_low = tilt_low if tilt_low is not None else config.tilt_low
        self._tilt_armed = {"left": True, "forward": True, "right": True, "back": True}

    def start_leds(self) -> None:
        """Paint the initial layer's LED feedback (call after the device opens)."""
        if self.leds is not None:
            self.leds.on_layer(self._layer())

    # --- event entry point --------------------------------------------------
    def handle(self, ev) -> Optional[ActionResult]:
        """Dispatch one decoded event. Returns the ActionResult if one ran."""
        # Imported lazily to avoid a hard dependency at module import time.
        from midifighter.device import (
            BankButton, ButtonDown, SideButton, Tilt,
        )

        if isinstance(ev, BankButton):
            return self._switch_layer(ev.index)
        if isinstance(ev, ButtonDown):
            res = self._fire(self._layer().pads.get(ev.pad), f"pad {ev.pad}")
            if self.leds is not None and self._layer().pads.get(ev.pad):
                self.leds.on_fire(ev.pad)
            return res
        if isinstance(ev, SideButton):
            return self._fire(self._layer().sides.get(ev.index), f"side {ev.index}")
        if isinstance(ev, Tilt):
            return self._handle_tilt(ev.edge, ev.value)
        return None

    # --- helpers ------------------------------------------------------------
    def _layer(self):
        return self.config.layers[self.current]

    def _switch_layer(self, bank_index: int) -> Optional[ActionResult]:
        idx = bank_index - 1
        if 0 <= idx < len(self.config.banks):
            self.current = self.config.banks[idx]
            self.on_fire(f"[layer] -> {self.current}")
            if self.leds is not None:
                self.leds.on_layer(self._layer())
        return None

    def _handle_tilt(self, edge: str, value: int) -> Optional[ActionResult]:
        if value >= self.tilt_high and self._tilt_armed.get(edge, True):
            self._tilt_armed[edge] = False
            return self._fire(self._layer().tilt.get(edge), f"tilt {edge}")
        if value <= self.tilt_low:
            self._tilt_armed[edge] = True
        return None

    def _fire(self, spec: Optional[dict], label: str) -> Optional[ActionResult]:
        if not spec:
            return None
        result = run_action(spec, dry_run=self.dry_run)
        tag = "would run" if self.dry_run else ("ran" if result.ok else "FAIL")
        self.on_fire(f"[{self.current}] {label}: {tag} {' '.join(result.argv)}"
                     + (f" ({result.detail})" if result.detail and not result.ok
                        else ""))
        return result
