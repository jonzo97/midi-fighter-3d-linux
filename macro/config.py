"""TOML config loader for the macro controller.

Parses a config file into a Config object of named Layers. Each layer maps pad
indices, tilt edges, and side buttons to action specs. Bank buttons select
layers by the ``[meta] banks`` order. Top-level ``[sides]`` are side-button
defaults for every layer; a layer's own ``sides`` override them, and
``{type = "none"}`` blanks one. ``[auto]`` drives the sway desk follower
(macro/desks.py).

Schema (see macro/config.toml for a full example):

    [meta]
    start = "sway"
    banks = ["sway", "review"]       # bank button 1->sway, 2->review, ...

    [sides]                          # every layer
    "2" = { type = "layer", to = "previous" }

    [layers.sway.pads]
    "0" = { type = "sway", cmd = "workspace number 1" }

    [layers.sway.tilt]
    forward = { type = "sway", cmd = "workspace next" }

    [layers.review.sides]            # overrides [sides] on this layer
    "1" = { type = "key", key = "z" }

    [auto]
    review_layer = "review"
    review_workspaces = [9, 10]
    tower_markers = ["Sanguine Spire"]

Key components:
    Layer, AutoConfig, Config -- parsed dataclasses
    load_config               -- parse + validate a TOML file
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field


@dataclass
class Layer:
    """One macro layer: pad/tilt/side action specs + an LED color."""
    name: str
    pads: dict[int, dict] = field(default_factory=dict)
    tilt: dict[str, dict] = field(default_factory=dict)
    sides: dict[int, dict] = field(default_factory=dict)
    color: str = "cyan"      # palette color for this layer's LED feedback


# Distinct palette colors auto-assigned to layers in definition order, unless
# overridden per layer via [meta] colors.<layer> = "name".
_LAYER_COLOR_CYCLE = ["cyan", "blue", "green", "magenta",
                      "orange", "purple", "yellow", "red"]


# Desk follower defaults: the private review desks and the Tower's page titles
# (matched in memory as substrings, case-insensitive, never logged).
DEFAULT_REVIEW_LAYER = "review"
DEFAULT_REVIEW_WORKSPACES = (9, 10)
DEFAULT_TOWER_MARKERS = ("Sanguine Spire", "Summoning Tower")

# Internal action types handled by the engine instead of macro.actions.
LAYER_ACTION = "layer"
NONE_ACTION = "none"
LAYER_TARGETS = ("previous", "show")
SIDE_COUNT = 6


@dataclass
class AutoConfig:
    """Desk follower settings ([auto]).

    Attributes:
        enabled: Follow sway focus at all.
        review_layer: Layer to switch to on a review desk.
        review_workspaces: Workspace numbers that are review desks.
        tower_markers: Title substrings that mean "the Tower is focused".
    """
    enabled: bool = False
    review_layer: str = DEFAULT_REVIEW_LAYER
    review_workspaces: tuple[int, ...] = DEFAULT_REVIEW_WORKSPACES
    tower_markers: tuple[str, ...] = DEFAULT_TOWER_MARKERS


# Tilt fires when the CC value rises past tilt_high, re-arms below tilt_low.
# Tilt CCs range 0..127; the device emits small stray values on bumps, so
# tilt_low sits above that noise floor. Lowered defaults = lighter tilt needed.
DEFAULT_TILT_HIGH = 45
DEFAULT_TILT_LOW = 18


@dataclass
class Config:
    """Full macro configuration."""
    start: str
    banks: list[str]
    layers: dict[str, Layer]
    tilt_high: int = DEFAULT_TILT_HIGH
    tilt_low: int = DEFAULT_TILT_LOW
    sides: dict[int, dict] = field(default_factory=dict)
    auto: AutoConfig = field(default_factory=AutoConfig)

    def layer(self, name: str) -> Layer | None:
        return self.layers.get(name)

    def side_action(self, layer_name: str, index: int) -> dict | None:
        """The action a side button runs on a layer: its override, else the default.

        Args:
            layer_name: Active layer.
            index: Side button 0..5.

        Returns:
            dict | None: The action spec, or None when blank or ``type = "none"``.
        """
        layer = self.layers.get(layer_name)
        spec = layer.sides.get(index) if layer is not None else None
        if spec is None:
            spec = self.sides.get(index)
        if not spec or spec.get("type") == NONE_ACTION:
            return None
        return spec


def _int_keys(d: dict, ctx: str) -> dict[int, dict]:
    """Convert string pad/side keys to ints, validating."""
    out: dict[int, dict] = {}
    for k, v in (d or {}).items():
        try:
            out[int(k)] = v
        except (TypeError, ValueError):
            raise ValueError(f"{ctx}: key {k!r} is not an integer index")
    return out


def _check_layer_actions(specs: dict, layers: dict, ctx: str) -> None:
    """Reject ``type = "layer"`` actions that point nowhere."""
    for key, spec in specs.items():
        if not isinstance(spec, dict):
            raise ValueError(f"{ctx} {key}: action must be a table")
        if spec.get("type") != LAYER_ACTION:
            continue
        target = spec.get("to")
        if target not in LAYER_TARGETS and target not in layers:
            raise ValueError(
                f"{ctx} {key}: layer action 'to' must be a layer or one of "
                f"{LAYER_TARGETS}; got {target!r}")


def _parse_auto(raw: dict, layers: dict) -> AutoConfig:
    """Parse and validate the [auto] desk follower table."""
    if not raw:
        return AutoConfig(enabled=False)
    review = str(raw.get("review_layer", DEFAULT_REVIEW_LAYER))
    enabled = bool(raw.get("enabled", True))
    if enabled and review not in layers:
        raise ValueError(f"[auto] review_layer {review!r} is not a defined layer")
    try:
        desks = tuple(int(n) for n in raw.get("review_workspaces",
                                               DEFAULT_REVIEW_WORKSPACES))
    except (TypeError, ValueError):
        raise ValueError("[auto] review_workspaces must be a list of numbers")
    markers = tuple(str(m) for m in raw.get("tower_markers",
                                            DEFAULT_TOWER_MARKERS) if str(m))
    return AutoConfig(enabled=enabled, review_layer=review,
                      review_workspaces=desks, tower_markers=markers)


def load_config(path: str) -> Config:
    """Load and validate a macro config from a TOML file.

    Args:
        path: Path to the .toml config.

    Returns:
        Config: Parsed configuration.

    Raises:
        FileNotFoundError: If the file is missing.
        ValueError: If the config is structurally invalid.
    """
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)

    meta = raw.get("meta", {})
    layers_raw = raw.get("layers", {})
    if not layers_raw:
        raise ValueError("config has no [layers]")

    color_overrides = meta.get("colors", {})
    layers: dict[str, Layer] = {}
    for i, (name, spec) in enumerate(layers_raw.items()):
        color = (spec.get("color") or color_overrides.get(name)
                 or _LAYER_COLOR_CYCLE[i % len(_LAYER_COLOR_CYCLE)])
        layers[name] = Layer(
            name=name,
            pads=_int_keys(spec.get("pads", {}), f"layer {name} pads"),
            tilt=dict(spec.get("tilt", {})),
            sides=_int_keys(spec.get("sides", {}), f"layer {name} sides"),
            color=color,
        )

    start = meta.get("start") or next(iter(layers))
    if start not in layers:
        raise ValueError(f"[meta] start = {start!r} is not a defined layer")
    banks = meta.get("banks", list(layers))
    for b in banks:
        if b not in layers:
            raise ValueError(f"[meta] banks references undefined layer {b!r}")

    sides = _int_keys(raw.get("sides", {}), "[sides]")
    for idx in sides:
        if not 0 <= idx < SIDE_COUNT:
            raise ValueError(f"[sides] index {idx} is not 0..{SIDE_COUNT - 1}")
    _check_layer_actions(sides, layers, "[sides]")
    for name, layer in layers.items():
        _check_layer_actions(layer.pads, layers, f"layer {name} pads")
        _check_layer_actions(layer.sides, layers, f"layer {name} sides")
        _check_layer_actions(layer.tilt, layers, f"layer {name} tilt")
    auto = _parse_auto(raw.get("auto", {}), layers)

    tilt_high = int(meta.get("tilt_high", DEFAULT_TILT_HIGH))
    tilt_low = int(meta.get("tilt_low", DEFAULT_TILT_LOW))
    if not 0 < tilt_low < tilt_high <= 127:
        raise ValueError(
            f"[meta] need 0 < tilt_low < tilt_high <= 127; got "
            f"tilt_low={tilt_low}, tilt_high={tilt_high}"
        )

    return Config(start=start, banks=banks, layers=layers,
                  tilt_high=tilt_high, tilt_low=tilt_low, sides=sides, auto=auto)
