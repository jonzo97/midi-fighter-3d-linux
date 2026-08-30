"""pygame renderer for the rhythm game — falling notes + HUD.

Draws 4 lanes with notes descending to a hit line, plus score/combo/accuracy and
a judgment popup. Pure presentation: it reads the engine and a song time, and
owns no game logic. Keyboard keys (D/F/J/K) mirror the 4 lanes so the game is
playable without the device.
"""

from __future__ import annotations

import pygame

from .engine import GameEngine, Judgement

WIDTH, HEIGHT = 520, 760
HIT_Y = 660
TOP_Y = 40
APPROACH_MS = 1500
KEY_LANES = {pygame.K_d: 0, pygame.K_f: 1, pygame.K_j: 2, pygame.K_k: 3}
_KEY_LABELS = ["D", "F", "J", "K"]

_LANE_COLORS = [(64, 200, 210), (70, 110, 240), (210, 90, 190), (240, 170, 60)]
_BG = (16, 16, 22)
_LANE_BG = (26, 26, 34)
_HIT_LINE = (200, 200, 210)
_JUDGE_COLOR = {
    Judgement.PERFECT: (90, 230, 120),
    Judgement.GREAT: (90, 230, 120),
    Judgement.GOOD: (235, 220, 90),
    Judgement.MISS: (235, 80, 80),
}


class GameRenderer:
    """Owns the pygame window and draws each frame.

    Args:
        lanes: Number of lanes.
        approach_ms: Time window a note is visible before its hit time.
    """

    def __init__(self, lanes: int = 4, approach_ms: int = APPROACH_MS) -> None:
        pygame.init()
        pygame.display.set_caption("MF3D Finger Drums")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.lanes = lanes
        self.approach = approach_ms
        self.lane_w = WIDTH / lanes
        self.font = pygame.font.SysFont("monospace", 22, bold=True)
        self.big = pygame.font.SysFont("monospace", 48, bold=True)
        self._popup_text = ""
        self._popup_color = (255, 255, 255)
        self._popup_until = 0

    def flash_judgement(self, judgement: Judgement, t_ms: int) -> None:
        """Show a judgment popup for a short time."""
        self._popup_text = judgement.value.upper()
        self._popup_color = _JUDGE_COLOR[judgement]
        self._popup_until = t_ms + 450

    def draw(self, engine: GameEngine, t_ms: int) -> None:
        """Render one frame."""
        self.screen.fill(_BG)
        self._draw_lanes()
        self._draw_notes(engine, t_ms)
        self._draw_hit_line()
        self._draw_hud(engine, t_ms)
        pygame.display.flip()

    # --- pieces -------------------------------------------------------------
    def _draw_lanes(self) -> None:
        for lane in range(self.lanes):
            x = int(lane * self.lane_w)
            pygame.draw.rect(self.screen, _LANE_BG,
                             (x + 2, 0, int(self.lane_w) - 4, HEIGHT))
            label = self.font.render(_KEY_LABELS[lane], True, (120, 120, 130))
            self.screen.blit(label, (x + self.lane_w / 2 - 8, HIT_Y + 40))

    def _draw_hit_line(self) -> None:
        pygame.draw.line(self.screen, _HIT_LINE, (0, HIT_Y), (WIDTH, HIT_Y), 3)

    def _draw_notes(self, engine: GameEngine, t_ms: int) -> None:
        for st in engine.upcoming(t_ms, self.approach):
            dt = st.note.time_ms - t_ms
            frac = 1.0 - dt / self.approach          # 0 at spawn, 1 at hit line
            y = TOP_Y + frac * (HIT_Y - TOP_Y)
            x = int(st.note.lane * self.lane_w)
            color = _LANE_COLORS[st.note.lane % len(_LANE_COLORS)]
            pygame.draw.rect(
                self.screen, color,
                (x + 8, int(y) - 12, int(self.lane_w) - 16, 24),
                border_radius=6,
            )

    def _draw_hud(self, engine: GameEngine, t_ms: int) -> None:
        hud = self.font.render(
            f"score {engine.score:>7}   x{engine.combo:<3}   "
            f"{engine.accuracy * 100:5.1f}%", True, (230, 230, 235))
        self.screen.blit(hud, (12, 10))
        if self._popup_until > t_ms and self._popup_text:
            surf = self.big.render(self._popup_text, True, self._popup_color)
            self.screen.blit(surf, (WIDTH / 2 - surf.get_width() / 2, HIT_Y - 140))

    @staticmethod
    def poll_events() -> tuple[bool, list[int]]:
        """Pump events. Returns (quit_requested, lanes_pressed_this_frame)."""
        quit_req = False
        lanes: list[int] = []
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                quit_req = True
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    quit_req = True
                elif ev.key in KEY_LANES:
                    lanes.append(KEY_LANES[ev.key])
        return quit_req, lanes
