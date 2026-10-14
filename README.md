# Midi Fighter 3D on Linux

Driver + apps for the DJ TechTools **Midi Fighter 3D**. No vendor driver, no
root — the device is class-compliant USB-MIDI. Three app tracks:

1. **Macro controller** — MF3D as a Sway/keystroke/game hotkey pad. **Works today.**
2. **LED light show** — animation engine (blocked on a one-time LED unblock; runs
   now against a terminal simulator).
3. **Finger-drum rhythm game** — pygame falling-notes (playable pre-LED; LED cues bonus).

**Key fact:** *input* (pads/tilt/rotate/buttons) works on Linux with no unblock.
Only LED *output* is gated by 4-Banks Mode (see [ADR-001](docs/adr/ADR-001-led-unblock-requires-utility.md) + [UNBLOCK-LEDS.md](docs/UNBLOCK-LEDS.md)).

📖 **[MIDIFIGHTER-3D-HACKING.md](docs/MIDIFIGHTER-3D-HACKING.md)** — the full
hardware-verified protocol + gotchas reference. Self-contained; publish-ready for
anyone hacking their own MF3D.

## Status

| Component | State | Notes |
|-----------|-------|-------|
| 0 — connection layer | ✅ verified | `smoke_test.py`: ports by name, send, receive |
| 1 — protocol discovery | ✅ input mapped | pads ch3 n36–51; buttons/tilt/rotate confirmed from 928-event capture |
| 2 — driver library | ✅ 15 tests | full input decode (incl. bank/side/rotate); LED output pending unblock |
| 3 — animation engine | ✅ 20 tests | terminal simulator works now; device LEDs pending unblock |
| **Macro controller** | ✅ 40 tests | `python -m macro.main` — Sway/keys/layers + LED feedback |
| 4 — rhythm game | ✅ 51 tests | `python -m game.main` — pygame falling-notes, LED cues, procedural audio |
| LED unblock | ✅ done | 4-Banks Mode disabled; LEDs live |

## Confirmed input map (from 928 captured events)

- **16 pads:** MIDI ch3, notes **36–51** (top-left → bottom-right).
- **Bank buttons:** ch4 notes 0–3. **Side buttons:** ch4 notes 38–43.
- **Tilt:** ch4 CC0–3 (left/forward/right/back). **Rotate:** ch4 CC36–51 (per pad, CC# = pad note).

## The blocker: 4-Banks Mode

LED-over-MIDI is disabled while 4-Banks Mode is on (factory default). Confirm it:
```bash
. .venv/bin/activate && python tools/diag_banks.py   # press banks 1-4 + pads
```
Disabling it is the current open task (native SysEx vs Wine + Midi Fighter Utility — under research).

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Verified facts (hardware)

- USB `2580:0005`, ALSA seq `24:0`, opens by name "Midi Fighter 3D" (never `hw:2` — dynamic).
- Color: Note-On on MIDI **ch 3**, velocity = palette color (10 hues × bright/dim).
- Animation: Note-On on MIDI **ch 4**, velocity = brightness/gate/pulse.
- Motion: tilt on **ch 4** CC0–3 — **CC1 (forward) confirmed live**.

## After banks mode is disabled — verify LEDs

Probe real pads (36–51) through the palette and a sweep; you should see color:
```bash
. .venv/bin/activate && python tools/probe_leds.py --mode colors --note 36 --dwell 0.6
. .venv/bin/activate && python tools/probe_leds.py --mode sweep --dwell 0.4
```
Then the echo demo lights the exact pad you press:
```bash
. .venv/bin/activate && python demo_echo.py
```

## Macro controller (works today)

Turn the MF3D into a Sway/keystroke hotkey pad. Bank buttons 1–4 switch layers
(16 pads × 4 banks). Safe preview first:

```bash
. .venv/bin/activate
python -m macro.main --dry-run     # prints what each input WOULD do
python -m macro.main               # live — fires real Sway/keystroke actions
```

Edit `macro/config.toml` to remap. Action types: `sway` (swaymsg), `key`/`text`
(wtype), `shell`, `notify`, `layer` (`to` = a layer, `previous` or `show`),
`none` (blank a side default). XWayland apps (Hydrus Client, Proton games) may
ignore wtype; that needs `ydotool` (uinput, sudo to set up), not done.

**Banks:** 1 sway desks · 2 window moves · 3 media · 4 **review** (hyAway's
review page: same pad, same verdict as the Tower's deck bank). The printable
map of all 4 banks × 16 pads + 6 side keys is [docs/CHEATSHEET.md](docs/CHEATSHEET.md),
generated from the config (`python tools/cheatsheet.py --write`).

**Side keys:** `[sides]` works on every bank; `[layers.<bank>.sides]` overrides.

**Desk follow (`[auto]`):** focus workspace 9 or 10 and the review bank switches
on; leave and your bank comes back; a bank press wins until the next desk
change. When the Tower page is the focused window (never checked on 9/10) the
pads, sides and tilt go quiet so the Tower's Web MIDI alone answers. Desks are
judged by number; titles are only substring-tested in memory for the Tower
marker and never logged. `--no-follow` turns it off.

**Autostart:** `contrib/systemd/mf3d-macro.service` (user unit; the enable
commands are in its header). It waits for the device at login and reconnects
after an unplug (`--wait-device`).

## Rhythm game

Finger-drumming falling-notes. Notes drop down 4 lanes; hit the matching pad
column (or keys **D/F/J/K**) on the beat. Procedural audio + a generated chart —
no files needed. LED cues light the bottom-row target pads and flash judgments.

```bash
. .venv/bin/activate
python -m game.main                     # generated demo song
python -m game.main --bpm 120 --bars 24 # faster, longer
python -m game.main --offset -40        # calibrate if you feel early/late (ms)
python -m game.main --beatmap song.json # a saved chart
```

Pad → lane is `pad % 4` (any pad in a column counts for that lane). Scoring:
Perfect ≤45ms, Great ≤90ms, Good ≤135ms, else Miss. Runs on keyboard alone with
`--no-device`.

## Layout

```
midifighter/        driver + LED engine package
  ports.py          dynamic port discovery (by name)
  protocol.py       verified wire constants + color <-> velocity maps
  device.py         MidiFighter3D class (I/O, delta-flush, geometry, decode)
  sinks.py          LedSink: DeviceSink (hardware) + TerminalSink (simulator)
  animations.py     frame engine + Reactive / RainbowSweep / Ripple
  showcase.py       python -m midifighter.showcase (terminal or device)
macro/              macro-controller app
  actions.py        sway/key/text/shell/notify backends
  config.py         TOML loader -> layers
  engine.py         MacroController (events -> actions, tilt debounce)
  desks.py          sway desk follower (review bank on 9/10, Tower mute)
  main.py           python -m macro.main [--dry-run] [--wait-device]
  config.toml       sway / window / media / review banks + side keys
game/               rhythm game
  beatmap.py        Note/Beatmap + procedural generator + JSON load/save
  engine.py         pygame-free scoring/timing core (unit tested)
  audio.py          procedural metronome + per-lane hit tones (numpy synth)
  leds.py           device LED cues (target column + judgment flash)
  render.py         pygame window (falling notes + HUD)
  main.py           python -m game.main
tools/
  capture_input.py  input logger -> capture_log.json
  probe_leds.py     LED sweep / palette / animation prober
  diag_banks.py     4-Banks Mode discriminator
  tilt_monitor.py   live tilt values -> pick a threshold
tests/              33 offline tests (no hardware)
smoke_test.py       connection check   demo_echo.py   press-to-light demo
docs/MIDIFIGHTER-3D-HACKING.md  full protocol + gotchas reference (publishable)
docs/UNBLOCK-LEDS.md   one-time LED unblock recipe
docs/adr/           architecture decision records
```
