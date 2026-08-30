"""Run the Midi Fighter 3D finger-drumming rhythm game.

Notes fall down 4 lanes; hit the matching pad (or D/F/J/K keys) on the beat.
Audio + a demo chart are generated procedurally — no files needed. When the
device is present, LED cues light the bottom-row target pads and flash judgments.

Examples:
    python -m game.main                       # generated demo song
    python -m game.main --bpm 120 --bars 24
    python -m game.main --beatmap song.json   # a saved chart
    python -m game.main --no-device           # keyboard only
    python -m game.main --offset -40          # audio/input calibration (ms)
"""

from __future__ import annotations

import argparse
import queue
import sys
import time

from midifighter.device import ButtonDown, MidiFighter3D
from midifighter.ports import DeviceNotFoundError
from midifighter.sinks import DeviceSink

from .audio import GameAudio
from .beatmap import generate_from_bpm, load_json
from .engine import GameEngine, Judgement
from .leds import GameLeds

COUNTDOWN_S = 2.0


def main(argv=None) -> int:
    """Run the game. Returns exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--beatmap", help="path to a JSON beatmap (else generated)")
    parser.add_argument("--bpm", type=float, default=100.0)
    parser.add_argument("--bars", type=int, default=16)
    parser.add_argument("--offset", type=int, default=0,
                        help="calibration offset in ms (+ = you hit late)")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--no-leds", action="store_true")
    parser.add_argument("--no-device", action="store_true")
    args = parser.parse_args(argv)

    try:
        beatmap = (load_json(args.beatmap) if args.beatmap
                   else generate_from_bpm(bpm=args.bpm, bars=args.bars))
    except (OSError, ValueError) as exc:
        print(f"[FAIL] beatmap: {exc}")
        return 1

    engine = GameEngine(beatmap)
    audio = GameAudio(enabled=not args.no_audio)
    hits: "queue.Queue[tuple[int, float]]" = queue.Queue()

    device = None
    if not args.no_device:
        try:
            def on_event(ev) -> None:
                if isinstance(ev, ButtonDown):
                    hits.put((ev.pad % beatmap.lanes, time.monotonic()))
            device = MidiFighter3D(on_event=on_event).open()
        except DeviceNotFoundError as exc:
            print(f"[warn] no device ({exc}); keyboard only (D/F/J/K)")

    leds = GameLeds(DeviceSink(device), lanes=beatmap.lanes) \
        if device is not None and not args.no_leds else None

    # Renderer imported lazily (needs a display).
    import pygame
    from .render import GameRenderer
    renderer = GameRenderer(lanes=beatmap.lanes)
    clock = pygame.time.Clock()

    print(f"'{beatmap.title}'  {beatmap.bpm:.0f} BPM  {engine.total_notes} notes. "
          f"Get ready...")
    t0 = time.monotonic() + COUNTDOWN_S     # song time 0 begins after countdown
    beat_ms = beatmap.beat_ms()
    next_beat = 0

    running = True
    while running:
        quit_req, key_lanes = renderer.poll_events()
        if quit_req:
            break
        now = time.monotonic()
        song_ms = int((now - t0) * 1000 + args.offset)

        # Device hits (timestamped at arrival) + keyboard hits (this frame).
        pending: list[tuple[int, int]] = []
        while not hits.empty():
            lane, ht = hits.get()
            pending.append((lane, int((ht - t0) * 1000 + args.offset)))
        pending += [(lane, song_ms) for lane in key_lanes]

        for lane, h_ms in pending:
            audio.hit(lane)
            res = engine.hit(lane, h_ms)
            if res is not None:
                _, judgement = res
                renderer.flash_judgement(judgement, song_ms)
                if leds is not None:
                    leds.on_judgement(lane, judgement, song_ms)

        # Metronome clicks on the beat (only once song has started).
        while next_beat * beat_ms <= song_ms:
            if song_ms >= 0:
                audio.click()
            next_beat += 1

        # Auto-miss notes past the window.
        for st in engine.update(song_ms):
            audio.miss()
            renderer.flash_judgement(Judgement.MISS, song_ms)
            if leds is not None:
                leds.on_judgement(st.note.lane, Judgement.MISS, song_ms)

        if leds is not None:
            leds.render(engine, song_ms)
        renderer.draw(engine, song_ms)

        if song_ms > beatmap.duration_ms:
            running = False
        clock.tick(60)

    _results(engine)
    if leds is not None:
        leds.clear()
    if device is not None:
        device.close()
    pygame.quit()
    return 0


def _results(engine: GameEngine) -> None:
    """Print a final score summary to the terminal."""
    c = engine.counts
    print("\n=== RESULTS ===")
    print(f"  score     {engine.score}")
    print(f"  accuracy  {engine.accuracy * 100:.1f}%")
    print(f"  max combo {engine.max_combo}")
    print(f"  perfect {c[Judgement.PERFECT]}  great {c[Judgement.GREAT]}  "
          f"good {c[Judgement.GOOD]}  miss {c[Judgement.MISS]}")


if __name__ == "__main__":
    sys.exit(main())
