#!/usr/bin/env python3
"""Render the printable Midi Fighter 3D cheat sheet from macro/config.toml.

The sheet (docs/CHEATSHEET.md) is generated, never hand-edited, so it can't
drift from the config; tests/test_review.py fails if the two disagree.

Run:
    python tools/cheatsheet.py            # print to stdout
    python tools/cheatsheet.py --write    # rewrite docs/CHEATSHEET.md

Key components:
    describe -- one action spec -> a short human label
    render   -- Config -> markdown text
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from macro.config import Config, load_config  # noqa: E402

CONFIG = os.path.join(ROOT, "macro", "config.toml")
SHEET = os.path.join(ROOT, "docs", "CHEATSHEET.md")
EMPTY = "·"
# Pad rows as seen from above, top row first (pad 0 = note 36 = bottom-left).
ROWS = [[12, 13, 14, 15], [8, 9, 10, 11], [4, 5, 6, 7], [0, 1, 2, 3]]
# Side buttons as (label, index), top to bottom. Inferred from the order the
# six were pressed in tools/capture_log.json (40,39,38 then 43,42,41).
SIDES = [("Left top", 2), ("Left middle", 1), ("Left bottom", 0),
         ("Right top", 5), ("Right middle", 4), ("Right bottom", 3)]
TILT_EDGES = ("forward", "back", "left", "right")


def describe(spec: dict | None) -> str:
    """A short label for an action spec (its ``label`` if it has one).

    Args:
        spec: Action dict from the config, or None.

    Returns:
        str: Human label, or the empty marker.
    """
    if not spec or spec.get("type") == "none":
        return EMPTY
    if spec.get("label"):
        return str(spec["label"])
    kind = spec.get("type")
    if kind == "key":
        return "+".join([*spec.get("mods", []), str(spec.get("key", ""))])
    if kind == "layer":
        return f"Layer: {spec.get('to')}"
    if kind in ("sway", "shell"):
        return str(spec.get("cmd", ""))
    return str(spec.get("text", kind))


def _cell(text: str) -> str:
    return text.replace("|", "/")


def render(cfg: Config) -> str:
    """Render the whole cheat sheet.

    Args:
        cfg: Parsed config.

    Returns:
        str: Markdown text ending in a newline.
    """
    out = ["# Midi Fighter 3D cheat sheet", "",
           "Generated from `macro/config.toml` by `python tools/cheatsheet.py "
           "--write`. Don't edit by hand.", "",
           "Pads are drawn as you look down at the grid, top row first."]
    if cfg.auto.enabled:
        desks = " or ".join(str(n) for n in cfg.auto.review_workspaces)
        out += ["", f"**Auto:** focus desk {desks} and bank "
                f"**{cfg.auto.review_layer}** switches on by itself; leave and "
                "your last bank comes back. A bank press wins until the next "
                "desk change. While the Tower page has focus the pads, sides "
                "and tilt are silent here (the Tower answers them itself)."]
    for i, name in enumerate(cfg.banks, start=1):
        layer = cfg.layers[name]
        out += ["", f"## Bank {i} · {name}", "",
                "| left | | | right |", "|---|---|---|---|"]
        for row in ROWS:
            out.append("| " + " | ".join(_cell(describe(layer.pads.get(p)))
                                         for p in row) + " |")
        tilts = [f"{edge} = {describe(layer.tilt[edge])}"
                 for edge in TILT_EDGES if layer.tilt.get(edge)]
        out += ["", "Tilt: " + (" · ".join(tilts) if tilts else "off")]

    override_layers = [n for n in cfg.banks if cfg.layers[n].sides]
    head = ["Side key", "Every bank"] + [f"Bank {cfg.banks.index(n) + 1} {n}"
                                         for n in override_layers]
    out += ["", "## Side keys", "",
            "| " + " | ".join(head) + " |",
            "|" + "---|" * len(head)]
    for label, idx in SIDES:
        cells = [f"{label} ({idx})", _cell(describe(cfg.sides.get(idx)))]
        for n in override_layers:
            own = cfg.layers[n].sides.get(idx)
            cells.append(_cell(describe(own)) if own else "")
        out.append("| " + " | ".join(cells) + " |")
    out += ["", "A blank override cell means the every-bank action. Which side "
            "is left, and which end is top, is inferred from the capture log: "
            "on bank 1 press **Which layer?** and if another key shows the "
            "notification, the sides are mirrored."]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    """Print or write the cheat sheet. Returns exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=CONFIG)
    parser.add_argument("--write", action="store_true",
                        help=f"rewrite {os.path.relpath(SHEET, ROOT)}")
    args = parser.parse_args(argv)
    try:
        text = render(load_config(args.config))
    except (OSError, ValueError) as exc:
        print(f"[FAIL] config: {exc}", file=sys.stderr)
        return 1
    if args.write:
        with open(SHEET, "w") as fh:
            fh.write(text)
        print(f"wrote {SHEET}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
