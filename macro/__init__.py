"""macro — turn the Midi Fighter 3D into a Sway/keystroke macro controller.

Input already works on Linux without any LED unblock, so this app is fully
usable today. Pad presses, tilt, rotation, and the bank/side buttons map to
actions (Sway commands, keystrokes, text, shell, notifications) via a TOML
config. Bank buttons switch between macro layers, giving 16 pads x 4 banks.

Key components:
    actions -- action backends (sway/key/type/shell/notify) + dispatch
    config  -- TOML loader -> Layer maps
    engine  -- MacroController wiring device events to actions
"""
