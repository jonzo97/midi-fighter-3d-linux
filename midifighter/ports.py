"""Dynamic Midi Fighter 3D port discovery.

The ALSA card index (e.g. ``hw:2``) is assigned at enumeration time and can
change between reboots or replugs, so ports are always resolved by NAME. This
module centralises that lookup so every app opens the correct device without
hard-coded indices, and without accidentally grabbing the "Midi Through" port.
"""

from __future__ import annotations

import mido

# Substrings used to identify the device port among all system MIDI ports.
DEVICE_NAME_HINTS = ("midi fighter 3d", "midi fighter")
# Ports that must never be selected even if a hint loosely matches.
EXCLUDE_HINTS = ("midi through", "through port")


class DeviceNotFoundError(RuntimeError):
    """Raised when no Midi Fighter 3D port can be located."""


def _match(name: str) -> bool:
    low = name.lower()
    if any(bad in low for bad in EXCLUDE_HINTS):
        return False
    return any(hint in low for hint in DEVICE_NAME_HINTS)


def find_output_name() -> str:
    """Return the exact name of the Midi Fighter 3D output port.

    Returns:
        str: The port name to pass to ``mido.open_output``.

    Raises:
        DeviceNotFoundError: If no matching output port is present.
    """
    for name in mido.get_output_names():
        if _match(name):
            return name
    raise DeviceNotFoundError(
        f"No Midi Fighter 3D output port. Available: {mido.get_output_names()}"
    )


def find_input_name() -> str:
    """Return the exact name of the Midi Fighter 3D input port.

    Returns:
        str: The port name to pass to ``mido.open_input``.

    Raises:
        DeviceNotFoundError: If no matching input port is present.
    """
    for name in mido.get_input_names():
        if _match(name):
            return name
    raise DeviceNotFoundError(
        f"No Midi Fighter 3D input port. Available: {mido.get_input_names()}"
    )
