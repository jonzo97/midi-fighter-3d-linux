"""Sway desk follower: review bank on the private desks, silence on the Tower.

Listens to ``swaymsg -t subscribe -m '["workspace","window"]'`` and drives the
MacroController:

    focus lands on a review desk (default workspaces 9 and 10)
        -> the review layer; the layer from before is remembered
    focus leaves the review desks
        -> that remembered layer comes back
    a bank button (or a "previous layer" side) on any desk
        -> wins until the next desk change (moving 9 -> 10 is a desk change)
    the focused window outside the review desks is the Tower page
        -> pads, sides and tilt are muted so the Tower's Web MIDI alone acts

Privacy contract (Jon's private desks):
    - Review desks are decided by workspace NUMBER only.
    - A window's title is looked at only to spot the Tower, only after sway
      has confirmed that THIS window (its con_id, via criteria) sits on a
      non-review desk, only as an in-memory substring test; it is never
      stored, logged or sent. A closed window or a failed query reads nothing.
    - Log lines carry workspace numbers and layer names, never titles or
      app ids. Errors are logged by exception class only.
    The raw event bytes do pass through this process's memory (sway sends
    whole containers); nothing here keeps them past the event.

Key components:
    parse_line          -- one subscribe line -> dict (or None)
    DeskFollower        -- pure state machine, fed event dicts (unit tested)
    focused_workspace   -- focused workspace number via get_workspaces
    window_on_public_desk -- is this con_id on a non-review desk? (criteria)
    SwayWatcher         -- background thread running the subscription
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import threading
from typing import Callable, Optional

SUBSCRIBE_EVENTS = ["workspace", "window"]
SWAYMSG = "swaymsg"
QUERY_TIMEOUT_S = 2.0
RETRY_MIN_S = 1.0
RETRY_MAX_S = 30.0


def parse_line(line: str) -> Optional[dict]:
    """Parse one line of ``swaymsg -t subscribe -m`` output.

    Args:
        line: Raw text line.

    Returns:
        dict | None: The event object, or None for blank/garbled/non-object lines.
    """
    if not line or not line.strip():
        return None
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def sway_env() -> Optional[dict]:
    """Environment for swaymsg, finding the socket again after a sway restart.

    Returns:
        dict | None: os.environ with a live SWAYSOCK, or None if there is none.
    """
    env = dict(os.environ)
    sock = env.get("SWAYSOCK")
    if sock and os.path.exists(sock):
        return env
    found = glob.glob(f"/run/user/{os.getuid()}/sway-ipc.*.sock")
    if not found:
        return None
    env["SWAYSOCK"] = max(found, key=os.path.getmtime)
    return env


def focused_workspace(env: Optional[dict] = None) -> Optional[int]:
    """Number of the focused sway workspace (get_workspaces holds no titles).

    Args:
        env: Environment with SWAYSOCK; found with sway_env() when None.

    Returns:
        int | None: The workspace number, or None if sway can't be asked.
    """
    env = env or sway_env()
    if env is None:
        return None
    try:
        out = subprocess.run([SWAYMSG, "-r", "-t", "get_workspaces"],
                             capture_output=True, text=True, env=env,
                             timeout=QUERY_TIMEOUT_S, check=False).stdout
        for ws in json.loads(out or "[]"):
            if isinstance(ws, dict) and ws.get("focused"):
                num = ws.get("num")
                return num if isinstance(num, int) else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return None


def public_desk_regex(review_workspaces) -> str:
    """Sway workspace-name regex matching every desk except the review ones.

    A workspace's number is its name's leading digits, so "9" and "9:media"
    are desk 9 while "90" is not.

    Args:
        review_workspaces: Iterable of review desk numbers.

    Returns:
        str: PCRE (sway criteria) pattern.
    """
    nums = "|".join(str(int(n)) for n in sorted(set(review_workspaces)))
    return f"^(?!(?:{nums})(?:[^0-9]|$))" if nums else "^"


def window_on_public_desk(con_id: int, review_workspaces,
                          env: Optional[dict] = None) -> Optional[bool]:
    """Ask sway whether one window sits on a non-review desk (no titles involved).

    Runs ``[con_id=N workspace="<public regex>"] nop``: success means the
    window exists and its desk is not a review desk.

    Args:
        con_id: The window's sway container id (from the event).
        review_workspaces: Review desk numbers.
        env: Environment with SWAYSOCK; found with sway_env() when None.

    Returns:
        bool | None: True if public, False if not (or gone), None if sway
        could not be asked.
    """
    if not isinstance(con_id, int) or isinstance(con_id, bool):
        return None
    env = env or sway_env()
    if env is None:
        return None
    rx = public_desk_regex(review_workspaces)
    try:
        out = subprocess.run(
            [SWAYMSG, "-r", f'[con_id={con_id} workspace="{rx}"] nop'],
            capture_output=True, text=True, env=env,
            timeout=QUERY_TIMEOUT_S, check=False).stdout
        replies = json.loads(out or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if not isinstance(replies, list) or not replies \
            or not isinstance(replies[0], dict):
        return None
    if replies[0].get("success") is True:
        return True
    return False if replies[0].get("error") == "No matching node." else None


class DeskFollower:
    """Turns sway workspace/window events into layer switches and Tower mute.

    Args:
        controller: The MacroController to drive.
        auto: AutoConfig (review layer, review desks, Tower markers).
        workspace_now: Callable returning the focused workspace number (or
            None); asked on every window focus event to catch desk changes.
            Defaults to focused_workspace.
        window_public: Callable(con_id) -> True only when sway confirms that
            window is on a non-review desk; the title is read only then.
            Defaults to window_on_public_desk.
        log: Callable(str) for title-free log lines.
    """

    def __init__(self, controller, auto,
                 workspace_now: Optional[Callable[[], Optional[int]]] = None,
                 window_public: Optional[Callable[[int], Optional[bool]]] = None,
                 log: Optional[Callable[[str], None]] = None) -> None:
        self.ctl = controller
        self.auto = auto
        self.workspace_now = workspace_now or focused_workspace
        self.window_public = window_public or (
            lambda con_id: window_on_public_desk(con_id,
                                                 self.auto.review_workspaces))
        self.log = log or (lambda _s: None)
        self.workspace: Optional[int] = None
        self._saved: Optional[str] = None     # layer from before the review desks

    @property
    def private(self) -> frozenset:
        return frozenset(self.auto.review_workspaces)

    def start(self, workspace: Optional[int]) -> None:
        """Set the starting desk (from focused_workspace())."""
        self.on_workspace(workspace)

    # --- events -------------------------------------------------------------
    def feed(self, payload: dict) -> None:
        """Handle one sway event object (workspace or window)."""
        if not isinstance(payload, dict):
            return
        change = payload.get("change")
        if "current" in payload:                       # workspace event
            if change == "focus":
                current = payload.get("current")
                num = current.get("num") if isinstance(current, dict) else None
                self.on_workspace(num if isinstance(num, int) else None)
            return
        container = payload.get("container")
        if not isinstance(container, dict):
            return
        if change == "focus":
            desk = self._ask_desk()
            if desk is not None and desk != self.workspace:
                self.on_workspace(desk)
        elif change == "title" and container.get("focused") is True:
            desk = self.workspace
        else:
            return
        if desk is None or desk in self.private:
            self.ctl.set_muted(False)                  # never look at the title
            return
        # The focused desk may have moved on since this event: confirm THIS
        # window's own desk before its title is looked at.
        if self._ask_public(container.get("id")) is not True:
            self.ctl.set_muted(False)
            return
        self.ctl.set_muted(self._is_tower(container))

    def on_workspace(self, num: Optional[int]) -> None:
        """A desk change: enter/leave the review desks, and unmute."""
        if num is None or num == self.workspace:
            return
        before, self.workspace = self.workspace, num
        # The window focus event that follows decides the Tower again.
        self.ctl.set_muted(False)
        was_private = before in self.private
        if num in self.private:
            if not was_private:
                self._saved = self.ctl.current
            self.ctl.set_layer(self.auto.review_layer, why=f"desk {num}")
        elif was_private:
            if self._saved:
                self.ctl.set_layer(self._saved, why=f"desk {num}")
            self._saved = None

    # --- helpers ------------------------------------------------------------
    def _ask_desk(self) -> Optional[int]:
        try:
            return self.workspace_now()
        except Exception as exc:  # noqa: BLE001 - a failed query must not kill the thread
            self.log(f"[desk] workspace query failed ({type(exc).__name__})")
            return None

    def _ask_public(self, con_id) -> Optional[bool]:
        try:
            return self.window_public(con_id)
        except Exception as exc:  # noqa: BLE001 - a failed query reads nothing
            self.log(f"[desk] window query failed ({type(exc).__name__})")
            return None

    def _is_tower(self, container: dict) -> bool:
        """In-memory marker test on a non-private window's title. Never logged."""
        title = container.get("name")
        if not isinstance(title, str) or not title:
            return False
        low = title.casefold()
        return any(m.casefold() in low for m in self.auto.tower_markers if m)


class SwayWatcher:
    """Runs the sway subscription in a daemon thread, reconnecting as needed.

    Args:
        follower: DeskFollower fed with every event.
        log: Callable(str) for title-free status lines.
    """

    def __init__(self, follower: DeskFollower,
                 log: Optional[Callable[[str], None]] = None) -> None:
        self.follower = follower
        self.log = log or (lambda _s: None)
        self._stop = threading.Event()
        self._proc: Optional[subprocess.Popen] = None
        self._thread = threading.Thread(target=self._run, name="sway-desks",
                                        daemon=True)

    def start(self) -> "SwayWatcher":
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop the thread and the swaymsg child it started."""
        self._stop.set()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=QUERY_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._thread.join(timeout=QUERY_TIMEOUT_S)

    def _run(self) -> None:
        delay = RETRY_MIN_S
        warned = False
        while not self._stop.is_set():
            env = sway_env()
            if env is None:
                if not warned:
                    self.log("[desk] no sway socket yet; desk follow waits")
                    warned = True
                self._stop.wait(delay)
                delay = min(delay * 2, RETRY_MAX_S)
                continue
            warned = False
            try:
                self._proc = subprocess.Popen(
                    [SWAYMSG, "-r", "-t", "subscribe", "-m",
                     json.dumps(SUBSCRIBE_EVENTS)],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, env=env)
            except OSError as exc:
                self.log(f"[desk] swaymsg failed to start ({type(exc).__name__})")
                self._stop.wait(delay)
                delay = min(delay * 2, RETRY_MAX_S)
                continue
            self.follower.start(focused_workspace(env))
            self.log(f"[desk] following sway; on workspace {self.follower.workspace}")
            for line in self._proc.stdout:
                if self._stop.is_set():
                    break
                payload = parse_line(line)
                del line
                if payload is None:
                    continue
                delay = RETRY_MIN_S
                try:
                    self.follower.feed(payload)
                except Exception as exc:  # noqa: BLE001 - keep following
                    self.log(f"[desk] event skipped ({type(exc).__name__})")
                del payload
            self._proc.wait()
            if not self._stop.is_set():
                self.log(f"[desk] sway subscription ended; retry in {delay:.0f}s")
                self._stop.wait(delay)
                delay = min(delay * 2, RETRY_MAX_S)
