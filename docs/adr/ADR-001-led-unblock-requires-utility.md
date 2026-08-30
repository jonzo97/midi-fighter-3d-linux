# ADR-001: LED control requires disabling 4-Banks Mode via the Windows/Mac Utility

## Status
Accepted

## Context
The Midi Fighter 3D ships in 4-Banks Mode (factory default). Per the official
User Guide (verified verbatim), in this mode the RGB LEDs **cannot** be driven
over MIDI — any MIDI-out just switches banks. We need per-pad LED control for the
light show and for rhythm-game/macro cueing.

We investigated whether the mode can be toggled from Linux without the vendor's
Windows/macOS "Midi Fighter Utility":
- **SysEx / EEPROM opcode:** none documented or found. DJTT never open-sourced
  the MF3D firmware (they did for the Twister — which is why *that* device is
  SysEx-configurable). No manufacturer SysEx ID or config protocol is public.
- **Hardware button-combo:** the "hold 4 corners on plug-in" combo only enters
  firmware-recovery/bootloader mode — it does not touch bank settings.
- **Wine:** one first-hand report — the Utility installs but never detects the
  device. No working recipe exists.

## Decision
Accept that **the one-time way to disable 4-Banks Mode is the official Midi
Fighter Utility on a Windows or macOS machine** (borrowed box or a VM with real
USB passthrough). The setting persists in device EEPROM, so it is needed only
once; afterward everything runs on pure Linux. Input (pads/tilt/rotate/buttons)
works on Linux regardless, so all input-driven apps are built and shipped
independent of this blocker.

## Consequences
- **Easier:** input-driven apps (macro controller, rhythm-game logic, animation
  engine tested via the terminal simulator) proceed with zero hardware blocker.
- **Harder:** visible hardware LEDs are gated on a one-time external step
  (documented in `docs/UNBLOCK-LEDS.md`).
- The LED protocol itself is confirmed correct (Note-On ch3, notes 36–51,
  velocity=palette color), so LED code carries no protocol risk once unblocked.

## Alternatives Considered
- **Reverse-engineer the config protocol** (usbmon capture while the Utility
  runs in a VM). Genuinely novel — no prior art for the MF3D. Deferred as an
  optional project, not the path to first light.
- **Wine.** Rejected as a primary plan (reported non-functional; long shot).

## Date
2026-07-02
