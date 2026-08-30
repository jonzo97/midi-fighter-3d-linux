"""midifighter — Linux driver + apps for the DJ TechTools Midi Fighter 3D.

The Midi Fighter 3D is a class-compliant USB-MIDI device. This package talks to
it over ALSA via python-rtmidi (through mido), with no root, no udev rule, and
no vendor driver required.

Key components:
    ports   -- dynamic port discovery (never hard-code ``hw:2``)
    device  -- MidiFighter3D driver class (Phase 2)
    protocol-- verified wire constants (Phase 1)
"""

__version__ = "0.1.0"
