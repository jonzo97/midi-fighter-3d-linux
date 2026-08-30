"""Action backends for the macro controller.

Each action is a small dict spec (from the TOML config) with a ``type`` and
type-specific fields. ``run_action`` turns a spec into an argv and executes it
(or, in dry-run mode, just returns what would run). Keystroke injection uses
``wtype`` on Wayland; game injection via ``ydotool`` (uinput-level) is a planned
backend — see notes below.

Spec examples:
    {type = "sway",   cmd = "workspace number 1"}
    {type = "key",    mods = ["ctrl", "shift"], key = "Left"}
    {type = "text",   text = "gg"}
    {type = "shell",  cmd = "grim ~/shot.png"}
    {type = "notify", text = "Bank 2"}
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class ActionResult:
    """Outcome of dispatching an action."""
    ok: bool
    argv: list[str]
    detail: str = ""


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def _build_argv(spec: dict) -> list[str]:
    """Translate an action spec into an argv list.

    Args:
        spec: The action dict from config.

    Returns:
        list[str]: Command argv. For shell actions, a single ``sh -c`` wrapper.

    Raises:
        ValueError: If the spec is malformed or the type is unknown.
    """
    kind = spec.get("type")
    if kind == "sway":
        cmd = spec.get("cmd")
        if not cmd:
            raise ValueError("sway action needs 'cmd'")
        return ["swaymsg", *str(cmd).split()]

    if kind == "key":
        key = spec.get("key")
        if not key:
            raise ValueError("key action needs 'key'")
        mods = spec.get("mods", []) or []
        # wtype: press mods, tap key, release mods (reverse order).
        argv = ["wtype"]
        for m in mods:
            argv += ["-M", str(m)]
        argv += ["-k", str(key)]
        for m in reversed(mods):
            argv += ["-m", str(m)]
        return argv

    if kind == "text":
        text = spec.get("text", "")
        return ["wtype", str(text)]

    if kind == "notify":
        text = spec.get("text", "")
        title = spec.get("title", "Midi Fighter 3D")
        return ["notify-send", str(title), str(text)]

    if kind == "shell":
        cmd = spec.get("cmd")
        if not cmd:
            raise ValueError("shell action needs 'cmd'")
        return ["sh", "-c", str(cmd)]

    raise ValueError(f"unknown action type: {kind!r}")


def run_action(spec: dict, dry_run: bool = False) -> ActionResult:
    """Execute an action spec (or preview it in dry-run mode).

    Args:
        spec: The action dict.
        dry_run: If True, do not execute — just return the argv.

    Returns:
        ActionResult: ok flag, the argv, and a detail message.
    """
    try:
        argv = _build_argv(spec)
    except ValueError as exc:
        return ActionResult(ok=False, argv=[], detail=str(exc))

    tool = argv[0]
    if not dry_run and not _have(tool):
        return ActionResult(ok=False, argv=argv, detail=f"{tool} not installed")

    if dry_run:
        return ActionResult(ok=True, argv=argv, detail="dry-run")

    try:
        subprocess.run(argv, check=False, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return ActionResult(ok=True, argv=argv)
    except (OSError, subprocess.SubprocessError) as exc:
        return ActionResult(ok=False, argv=argv, detail=str(exc))
