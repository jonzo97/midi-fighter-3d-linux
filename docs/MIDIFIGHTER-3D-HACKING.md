# Hacking the DJ TechTools Midi Fighter 3D

A field-verified reference for programming the **Midi Fighter 3D** (MF3D) from
code on Linux (works on macOS/Windows too — it is the same USB-MIDI device).
Everything here was confirmed on real hardware, or is flagged where it wasn't.
Written so anyone who wants to drive the pads and LEDs from their own software
doesn't have to re-derive the protocol from a 928-event capture like we did.

> **TL;DR** — The MF3D is a class-compliant USB-MIDI device. No vendor driver,
> no root. **Input works out of the box.** LED *output* is silently blocked by
> one factory setting (4-Banks Mode) that can only be flipped in the Windows/Mac
> Midi Fighter Utility. Colors are chosen by Note-On **velocity**, not by RGB.

---

## 1. Hardware facts (verified on our unit)

| Property | Value |
|----------|-------|
| USB VID:PID | `2580:0005` |
| Device class | Class-compliant USB-MIDI (audio class) — **no driver needed** |
| ALSA seq | enumerates as `Midi Fighter 3D` (e.g. `24:0`), rawmidi `hw:2,0,0` |
| Grid | 16 arcade pads, 4×4 |
| Extra input | 6 side buttons, 4 bank buttons, per-pad **rotation** encoder, 3-axis **tilt** |
| LEDs | per-pad RGB, palette-selected (not free 24-bit) |
| Power | bus-powered |

**Never hard-code `hw:2`.** The ALSA card number is assigned at plug time and
moves. Open the port **by name substring** (`"midi fighter"`) — see §6.

The MF3D firmware is **not** open source; DJTT never released it. There is no
SysEx or hardware path to change device settings from Linux. The Midi Fighter
Utility (Windows/Mac, a Chromium app) is the only way to change persistent
config. This matters for the LED blocker in §5.

---

## 2. Channel model

Base channel is **3** (factory default), and the device uses two consecutive
channels:

| Purpose | MIDI channel (1-indexed) | Notes |
|---------|--------------------------|-------|
| Pad Note-On/Off (input) | **3** | which pad you pressed |
| Pad **color** (LED output) | **3** | Note-On, velocity = palette color |
| **Animation** (LED output) | **4** | Note-On, velocity = brightness/gate/pulse |
| Tilt / rotate / bank / side (input) | **4** | CCs + notes, see §3 |

> **Off-by-one trap:** MIDI channels are 1-indexed by convention (ch 1–16) but
> `mido` / `python-rtmidi` are **0-indexed**. MIDI ch 3 = mido `channel=2`.
> Store the human number, convert at the wire: `mido_ch = midi_ch - 1`.

---

## 3. Input protocol (works with zero setup)

All of this streams the moment you open the input port. No unblock required.

### Pads — MIDI ch 3, Note-On notes **36–51**

4×4 grid, top-left → bottom-right, row-major:

```
note = 36 + row*4 + col      # row 0 = top,  col 0 = left
row, col = divmod(note-36, 4)
```

Verified: **note 36 = bottom-left / physical origin** on our unit (confirmed by
the light-echo probe). If your grid looks rotated vs. your code, that's an
orientation-calibration step, not a protocol error.

### Rotation encoder — MIDI ch 4, **CC = the pad's note number**

Each pad twists. Rotating the pad whose note is `N` emits `control_change` on
ch 4 with `control=N` (so CC 36–51). Value is the encoder position/delta.

### Tilt (3-axis motion) — MIDI ch 4, CC 0–3

| Edge | CC |
|------|----|
| Left | 0 |
| Forward | 1 *(verified live)* |
| Right | 2 |
| Back | 3 |

Value 0–127. Tilt is **analog and noisy** — debounce it. Our macro layer fires
on a rising threshold (≈45/127) and re-arms only after it falls back under a
low threshold (≈18/127). Raw thresholds of 100+ "need to tilt way too far";
tune with a live monitor and expose the thresholds as config.

### Bank buttons — MIDI ch 4, Note-On notes **0–3**

The four corner mode buttons. See the 4-Banks warning in §5.

### Side buttons — MIDI ch 4, Note-On notes **38–43** (6 buttons)

> Side-button notes (38–43) collide numerically with pad notes (36–51) but live
> on a **different channel** (4 vs 3). Always disambiguate on (channel, note),
> never note alone.

---

## 4. LED output protocol

### Color — Note-On on ch 3, velocity picks the color

LEDs are **not** 24-bit RGB. You get a palette of **10 hues × {bright, dim}**,
selected by the Note-On velocity:

| Color | bright vel | dim vel |
|-------|-----------:|--------:|
| red | 13 | 19 |
| orange | 25 | 31 |
| yellow | 37 | 43 |
| lime | 49 | 55 |
| green | 61 | 67 |
| cyan | 73 | 79 |
| blue | 85 | 91 |
| purple | 97 | 103 |
| magenta | 109 | 115 |
| white | 121 | 5 |

- `velocity = 0` → **release** the MIDI LED override (pad returns to its own state).
- The palette occupies velocities **13–120** as 18 contiguous 6-wide bands
  (9 hues × bright/dim). White sits at the edges (0–12 dim, 121–127 bright).
- **Velocities 121–127 are special:** they force the Utility-configured "active
  color." Avoid them for animation — you'll get a color you didn't ask for.

Light pad `note` cyan-bright: `note_on(channel=2, note=note, velocity=73)`.

### Animation — Note-On on ch 4, velocity picks the effect

| Effect | velocity range | notes |
|--------|---------------:|-------|
| Brightness (16 levels, VU-style) | 18–33 | 0%→100% |
| Gate (8 flash rates) | 34–41 | |
| Pulse (8 pulse rates) | 42–49 | |
| Off | 0 | |

Brightness is the useful one for meters: map `0.0..1.0` linearly onto 18–33.

---

## 5. The big gotcha: 4-Banks Mode blocks all LED output

**Factory default has "Four Banks Mode" ON, and it silently swallows every LED
command.** Note-On writes to the color channel are *accepted* (the ALSA write
returns success) but **nothing lights up**. This burns hours because "the write
succeeded" reads like it worked.

You cannot disable it from Linux (no open firmware, no SysEx path). Fix, once:

1. On a **Windows or Mac** box, open the **Midi Fighter Utility**.
2. Connect the MF3D. Find the **"Four Banks Mode"** setting → set it to
   **Disabled**. (This is the *mode setting*, not "disable the bank buttons.")
3. Pick a bank-button behavior (Hold is fine).
4. Click **Send to Midi Fighter** to write it to EEPROM. Reconnect.

After that, LEDs respond over MIDI on Linux forever (setting is persistent).

**Diagnosing it:** if input works but no pad ever lights regardless of velocity,
suspect 4-Banks Mode before you suspect your color math. A dark panel with
*working input* is almost always a config/power problem, not a wire-format bug.

**Serial-fill is normal:** writing 16 pads sends 16 messages down one bulk
endpoint, so a full-grid repaint visibly fills left→right, bottom row first,
rather than all at once. Not a bug — it's serial MIDI. Minimize it with delta
writes (§6).

---

## 6. Programming patterns that paid off

These are device-agnostic enough to reuse on any USB-MIDI grid controller
(Launchpad, APC, etc.).

**Discover ports by name, never by index.** Card numbers move between plugs.
Match a lowercase substring and exclude the ALSA "Midi Through" port.

```python
def find_port(names, hint=("midi fighter", "midi fighter 3d")):
    return next(n for n in names
                if any(h in n.lower() for h in hint)
                and "through" not in n.lower())
```

**Shadow + delta writes.** Keep the last velocity written per pad; skip the
Note-On if it's unchanged. On a serial endpoint this is the difference between a
smooth 60 Hz refresh and a flickering, lagging grid.

**Rate-limit the flush.** Buffer pad changes and flush the delta at a fixed cap
(we used 60 Hz). Flooding the bulk endpoint every state change stalls it.

**Split pure logic from I/O for tests.** Keep the animation/scoring/decode logic
free of MIDI, time, and the window toolkit, so it's deterministic and unit-
testable. The I/O layer (open port, send bytes, read clock) is a thin shell over
it. Our whole engine tested headless with zero hardware.

**Capture-driven reverse engineering.** When a mapping is unknown, log raw
events to JSON while you exercise every control by hand, then derive the map from
data instead of guessing. One 928-event capture nailed the entire input protocol
(pad notes, rotate CCs, side/bank channels) in one pass.

**Write ADRs for the dead ends.** We wrote down "LED unblock requires the
Utility; there is no native Linux path" as a decision record so no future
session re-investigates a native SysEx unlock that doesn't exist.

---

## 7. Gotcha cheat sheet

- Input works with **no** unblock; LED output needs 4-Banks Mode **off**.
- LED write "succeeding" ≠ LED lighting. Confirm visually.
- Color is chosen by **velocity**, not RGB. 10 hues × bright/dim only.
- Velocity **121–127** hijacks your color (forces Utility active color).
- MIDI ch is 1-indexed; mido is 0-indexed. `mido_ch = midi_ch - 1`.
- Same note number appears on ch 3 (pad) and ch 4 (side button) — key on
  **(channel, note)**.
- Never hard-code `hw:2`. Open **by name**.
- Tilt is analog + noisy — **debounce with hysteresis**, thresholds ≈45↑/18↓.
- Full-grid repaint fills serially (bottom-left first) — expected, not a bug.

---

## 8. References

- Midi Fighter User Guide v1.03 — color table (Fig 2), animation bands, motion CCs.
- Midi Fighter Utility (Windows/Mac) — the only way to change persistent config.
- `python-rtmidi` + `mido` — cross-platform MIDI I/O used throughout.
- This repo — a working driver (`midifighter/`), a Sway macro pad (`macro/`), and
  a finger-drum rhythm game (`game/`) built on the above.

---

*Verified on hardware, 2026-08. Corrections welcome — the point of publishing
this is that the next person doesn't lose an afternoon to 4-Banks Mode.*
