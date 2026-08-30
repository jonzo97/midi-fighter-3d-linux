# Unblocking the LEDs — disable 4-Banks Mode (one-time)

The Midi Fighter 3D ships in **4-Banks Mode**, which blocks all LED control over
MIDI (writes just switch banks). This is stored in the device's EEPROM and can
only be changed with the official **Midi Fighter Utility** (Windows/macOS). Do
this **once** on any borrowed Win/Mac machine — the setting persists on the
device, so afterward everything runs on pure Linux forever.

There is no native-Linux or SysEx path (DJTT never open-sourced the MF3D
firmware; Wine fails to detect the device). Confirmed by manual + research.

## Steps (~5 minutes on a Windows or Mac box)

1. **Download the Midi Fighter Utility:**
   https://store.djtechtools.com/pages/midi-fighter-utility
   (grab the current Windows or macOS build).

2. **Plug in the Midi Fighter 3D** via USB, then launch the Utility. It should
   auto-detect the device (top of window shows "Midi Fighter 3D").

3. **Open the settings** — look for the **"Four Banks Mode"** option (in the
   device/global settings panel).

4. **Set "Four Banks Mode" to `Disabled`.**
   - You'll also choose bank-button behaviour: **Hold** vs **Toggle**.
     - **Hold** → you additionally get independent LED control on the 4 bank
       buttons (recommended if you want to light them).
     - **Toggle** → bank-button LEDs just reflect toggle state.
   - Either is fine for the arcade-pad light show; **Hold** gives more control.

5. **Click "Send to Midi Fighter"** (or File → Send) to write the setting to
   the device EEPROM. Some versions auto-send on change — make sure it persists.

6. **(Optional) Export settings** as a backup (Tools → Export) in case of a
   later factory reset.

7. Unplug, bring the device back to Linux.

## Verify on Linux

```bash
cd ~/midi && . .venv/bin/activate

# Should now SHOW color on the top-left pad region (notes 36-51):
python tools/probe_leds.py --mode colors --note 36 --dwell 0.6
python tools/probe_leds.py --mode sweep --dwell 0.4

# Press-to-light:
python demo_echo.py

# Full light show:
python -m midifighter.showcase --sink device
```

If pads light up in color: **done** — 4-Banks Mode is off for good and the
whole animation engine + rhythm-game LED layer come alive.

## If you can't borrow a machine

- **VM route:** a Windows/macOS guest with genuine USB passthrough
  (VirtualBox/QEMU) works because the guest gets a native USB stack. More setup
  than a borrowed box but fully DIY.
- **Wine:** long shot — reported to install but not detect the device. Not
  recommended as a primary plan.
