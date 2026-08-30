"""game — a finger-drumming rhythm game for the Midi Fighter 3D.

Notes fall down 4 lanes (the device's columns); hit the matching pad in time.
Input works on Linux with no LED unblock, so the game is fully playable on
screen; when the device is present, LED cues light the target column and flash
the judgment. Audio + a demo beatmap are generated procedurally (no asset files
needed); real tracks load from JSON beatmaps.

Key components:
    beatmap -- Note/Beatmap data + procedural generator + JSON load/save
    engine  -- pygame-free scoring/timing core (unit tested)
    audio   -- procedural metronome + per-lane hit sounds (pygame.mixer)
    leds    -- device LED cueing (target column + judgment flash)
    render  -- pygame window (falling notes + HUD)
    main    -- wires input + audio + engine + render
"""

__version__ = "0.1.0"

LANES = 4
