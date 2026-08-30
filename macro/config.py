"""TOML config loader for the macro controller.

Parses a config file into a Config object of named Layers. Each layer maps pad
indices, tilt edges, and side buttons to action specs. Bank buttons select
layers by the ``[meta] banks`` order.

Schema (see macro/config.toml for a full example):

    [meta]
    start = "sway"
    banks = ["sway", "helldivers"]   # bank button 1->sway, 2->helldivers, ...

    [layers.sway.pads]
    "0" = { type = "sway", cmd = "workspace number 1" }

    [layers.sway.tilt]
    forward = { type = "sway", cmd = "workspace next" }

    [layers.sway.sides]
    "0" = { type = "notify", text = "hi" }
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

    def layer(self, name: str) -> Layer | None:
        return self.layers.get(name)


def _int_keys(d: dict, ctx: str) -> dict[int, dict]:
    """Convert string pad/side keys to ints, validating."""
    out: dict[int, dict] = {}
    for k, v in (d or {}).items():
        try:
            out[int(k)] = v
        except (TypeError, ValueError):
            raise ValueError(f"{ctx}: key {k!r} is not an integer index")
    return out


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

    tilt_high = int(meta.get("tilt_high", DEFAULT_TILT_HIGH))
    tilt_low = int(meta.get("tilt_low", DEFAULT_TILT_LOW))
    if not 0 < tilt_low < tilt_high <= 127:
        raise ValueError(
            f"[meta] need 0 < tilt_low < tilt_high <= 127; got "
            f"tilt_low={tilt_low}, tilt_high={tilt_high}"
        )

    return Config(start=start, banks=banks, layers=layers,
                  tilt_high=tilt_high, tilt_low=tilt_low)
