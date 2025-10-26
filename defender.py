"""
Side-scrolling Defender-style arcade game implemented with pygame.

This module contains everything required to run the game: gameplay constants,
entity definitions, sound synthesis, rendering, collision handling, and the main
event loop.  The code favours readability and explicable state transitions so
that the classic Defender rule-set can serve as a reference-quality example for
retro arcade mechanics implemented in Python.
"""

from __future__ import annotations

import math
import random
from array import array
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence, Union
import heapq

import pygame


# Screen and world configuration ------------------------------------------------
SCREEN_WIDTH = 1180
SCREEN_HEIGHT = 760
WORLD_WIDTH = 6000
FPS = 60
HUD_HEIGHT = 110
PLAYFIELD_TOP = HUD_HEIGHT + 60

# Gameplay tuning ----------------------------------------------------------------
PLAYER_SPEED = 320
PLAYER_VERTICAL_SPEED = 260
PLAYER_FIRE_COOLDOWN = 0.18
PLAYER_BULLET_SPEED = 700
PLAYER_RESPAWN_INVULN = 2.5
PLAYER_DEATH_INVULN = 2.0
PLAYER_DEATH_RESPAWN_DELAY = 2.0
PLAYER_ACCEL = 520
PLAYER_MAX_SPEED = 520
PLAYER_CRUISE_SPEED = 120
ENGINE_DAMPING = 320

LANDER_MIN_ALTITUDE = 120
LANDER_SPEED = 80
LANDER_ASCENT_SPEED = 90
LANDER_DESCENT_SPEED = 110
LANDER_FIRE_INTERVAL = (2.4, 4.8)
LANDER_SHOT_SPEED = 260
LANDER_SPAWN_INTERVAL = 4.0
LANDER_TOP_COLOR = (255, 255, 0)
LANDER_BODY_COLOR = (0, 255, 0)
LANDER_LEG_COLOR = (0, 200, 0)
CAPTURED_HUMAN_COLOR = (255, 0, 255)

MUTANT_SPEED = 190
MUTANT_FIRE_INTERVAL = (1.2, 2.0)
MUTANT_SHOT_SPEED = 340

HUMAN_COUNT = 10
HUMAN_SPACING = WORLD_WIDTH // HUMAN_COUNT
HUMAN_POSITIONS = [i * HUMAN_SPACING + HUMAN_SPACING // 2 for i in range(HUMAN_COUNT)]
GRAVITY = 168
TERMINAL_VELOCITY = 480
SAFE_LANDING_HEIGHT_RATIO = 1.0 / 3.0

BOMBER_SPEED = 150
BOMBER_DROP_INTERVAL = (1.8, 3.6)
MINE_TTL = 12.0

POD_SPEED = 90
POD_VERTICAL_RANGE = 90
POD_SWARMER_COUNT = (4, 6)

SWARMER_SPEED = 240
SWARMER_JITTER = 80

BAITER_SPEED = 260
BAITER_FIRE_INTERVAL = (0.9, 1.6)
BAITER_SPAWN_DELAY = 35.0
BAITER_STALL_WARNING = 45.0

GROUND_BASELINE = SCREEN_HEIGHT - 110
GROUND_PRIMARY_AMPLITUDE = 55
GROUND_SECONDARY_AMPLITUDE = 28

STAR_LAYERS = 3
STARS_PER_LAYER = 90
STAR_COLORS = [(90, 90, 90), (150, 150, 180), (200, 200, 220)]

THRUSTER_COLORS = [
    (255, 80, 40),
    (255, 180, 60),
    (255, 240, 150),
    (200, 120, 255),
]

POPUP_COLORS = [
    (255, 80, 220),
    (255, 200, 60),
    (120, 255, 220),
    (255, 255, 255),
]
DEFAULT_HINT = "Press Enter to launch. WASD/Arrows move, Space fire, Shift warp turn, B smart bomb, H hyperspace, 0 no-death."
SMART_BOMB_KEY = pygame.K_b
HYPERSPACE_KEY = pygame.K_h
HYPERSPACE_COOLDOWN = 5.0

DEMO_CONTROL_KEYS = [
    pygame.K_LEFT,
    pygame.K_RIGHT,
    pygame.K_UP,
    pygame.K_DOWN,
    pygame.K_SPACE,
]
HYPERSPACE_LOCK_DURATION = 0.12
HYPERSPACE_VANISH_TIME = 0.06
HYPERSPACE_REAPPEAR_DELAY = 0.09
HYPERSPACE_REAPPEAR_TIME = 0.06
HYPERSPACE_STABILIZE_TIME = 0.09
SMART_BOMB_KEY = pygame.K_b
HYPERSPACE_KEY = pygame.K_h
HYPERSPACE_COOLDOWN = 5.0


# Sound synthesis ----------------------------------------------------------------
class SoundManager:
    """Builds and plays the retro soundscape entirely via procedural synthesis."""
    def __init__(self):
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init()
            except pygame.error:
                self.enabled = False
                self.sounds = {}
                return
        self.enabled = True
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.looping: dict[str, Optional[pygame.mixer.Channel]] = {}
        self.sample_rate = 44100
        self._build_sounds()

    def _build_sounds(self):
        """Create and cache all sound effects used throughout the game."""
        self.sounds["player_fire"] = self._chirp(2200, 700, 0.12, 0.4, waveform="square", harmonic=0.25, vibrato=0.05)
        self.sounds["enemy_fire"] = self._chirp(950, 450, 0.18, 0.35, waveform="triangle", vibrato=0.08)
        self.sounds["explosion"] = self._explosion(0.6, 0.45)
        self.sounds["human_pick"] = self._arpeggio([900, 1200, 1600], 0.05, 0.28)
        self.sounds["human_drop"] = self._arpeggio([1600, 1200, 900], 0.06, 0.28)
        self.sounds["mutate"] = self._chirp(400, 900, 0.35, 0.38, waveform="saw", vibrato=0.12)
        self.sounds["baiter"] = self._sustain_tone(320, 0.8, 0.3, vibrato=0.2)
        self.sounds["mine"] = self._blip(0.18, 0.3)
        self.sounds["engine"] = self._sustain_tone(110, 0.5, 0.25, vibrato=0.15)
        self.sounds["smart_bomb"] = self._explosion(0.9, 0.6)
        self.sounds["hyperspace_in"] = self._arpeggio([700, 1100, 1500], 0.06, 0.35)
        self.sounds["hyperspace_out"] = self._blip(0.1, 0.35)

    def _wave(self, phase: float, waveform: str) -> float:
        cycle = (phase / (2 * math.pi)) % 1.0
        if waveform == "square":
            return 1.0 if cycle < 0.5 else -1.0
        if waveform == "saw":
            return 2.0 * cycle - 1.0
        if waveform == "triangle":
            return 1.0 - 4.0 * abs(round(cycle - 0.25) - (cycle - 0.25))
        return math.sin(phase)

    def _chirp(self, start_freq: float, end_freq: float, duration: float, volume: float, *, waveform: str = "square", harmonic: float = 0.0, vibrato: float = 0.0) -> pygame.mixer.Sound:
        total_samples = int(self.sample_rate * duration)
        data = array('h')
        phase = 0.0
        harmonic_phase = 0.0
        for i in range(total_samples):
            progress = i / max(1, total_samples - 1)
            freq = start_freq + (end_freq - start_freq) * progress
            if vibrato:
                freq *= 1.0 + vibrato * math.sin(progress * math.pi * 6)
            delta = 2 * math.pi * freq / self.sample_rate
            phase += delta
            value = self._wave(phase, waveform)
            if harmonic > 0.0:
                harmonic_phase += delta * 2
                value = (1 - harmonic) * value + harmonic * self._wave(harmonic_phase, waveform)
            envelope = (1 - progress) ** 1.8
            sample = int(32767 * volume * envelope * max(-1.0, min(1.0, value)))
            data.append(sample)
        return pygame.mixer.Sound(buffer=data)

    def _explosion(self, duration: float, volume: float) -> pygame.mixer.Sound:
        total_samples = int(self.sample_rate * duration)
        data = array('h')
        phase = 0.0
        for i in range(total_samples):
            progress = i / max(1, total_samples - 1)
            amp = volume * (1 - progress) ** 2
            phase += 2 * math.pi * (60 + 120 * (1 - progress)) / self.sample_rate
            rumble = math.sin(phase)
            noise = random.uniform(-1.0, 1.0)
            sample = int(32767 * amp * max(-1.0, min(1.0, 0.6 * noise + 0.4 * rumble)))
            data.append(sample)
        return pygame.mixer.Sound(buffer=data)

    def _arpeggio(self, freqs: list[float], note_time: float, volume: float) -> pygame.mixer.Sound:
        duration = len(freqs) * note_time
        total_samples = int(self.sample_rate * duration)
        data = array('h')
        phase = 0.0
        for i in range(total_samples):
            t = i / self.sample_rate
            index = min(len(freqs) - 1, int(t / note_time))
            freq = freqs[index]
            phase += 2 * math.pi * freq / self.sample_rate
            envelope = max(0.0, 1 - (t / duration))
            sample = int(32767 * volume * envelope * math.sin(phase))
            data.append(sample)
        return pygame.mixer.Sound(buffer=data)

    def _sustain_tone(self, freq: float, duration: float, volume: float, *, vibrato: float = 0.0) -> pygame.mixer.Sound:
        total_samples = int(self.sample_rate * duration)
        data = array('h')
        phase = 0.0
        for i in range(total_samples):
            progress = i / max(1, total_samples - 1)
            mod = math.sin(progress * math.pi * 10) * vibrato
            effective_freq = freq * (1 + mod * 0.3)
            phase += 2 * math.pi * effective_freq / self.sample_rate
            envelope = volume * (0.5 + 0.5 * math.sin(progress * math.pi))
            sample = int(32767 * envelope * self._wave(phase, "triangle"))
            data.append(sample)
        return pygame.mixer.Sound(buffer=data)

    def _blip(self, duration: float, volume: float) -> pygame.mixer.Sound:
        total_samples = int(self.sample_rate * duration)
        data = array('h')
        phase = 0.0
        for i in range(total_samples):
            progress = i / max(1, total_samples - 1)
            freq = 600 + 200 * math.sin(progress * math.pi * 2)
            phase += 2 * math.pi * freq / self.sample_rate
            envelope = volume * (1 - progress) ** 2
            wave = self._wave(phase, "square")
            sample = int(32767 * envelope * wave)
            data.append(sample)
        return pygame.mixer.Sound(buffer=data)

    def play(self, key: str):
        if not self.enabled:
            return
        sound = self.sounds.get(key)
        if sound:
            sound.play()

    def loop(self, key: str):
        if not self.enabled:
            return
        sound = self.sounds.get(key)
        if not sound:
            return
        channel = self.looping.get(key)
        if channel and channel.get_busy():
            return
        channel = sound.play(loops=-1)
        if channel:
            self.looping[key] = channel

    def stop(self, key: str):
        channel = self.looping.pop(key, None)
        if channel:
            channel.stop()


# Helper utilities ----------------------------------------------------------------
def wrap_position(x: float) -> float:
    """Wrap a world X coordinate into [0, WORLD_WIDTH)."""
    if x < 0:
        x += WORLD_WIDTH
    elif x >= WORLD_WIDTH:
        x -= WORLD_WIDTH
    return x


def shortest_offset(a: float, b: float) -> float:
    """Return shortest signed offset between two world X positions."""
    raw = (a - b) % WORLD_WIDTH
    if raw > WORLD_WIDTH / 2:
        raw -= WORLD_WIDTH
    return raw


def world_to_screen(x: float, camera_x: float) -> float:
    """Convert world X to screen X using wrapped offset."""
    offset = shortest_offset(x, camera_x)
    return offset + SCREEN_WIDTH / 2


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def terrain_height(x: float) -> float:
    """Compute the rolling landscape height for a given world X."""
    x = x % WORLD_WIDTH
    primary = math.sin(x * 0.004) * GROUND_PRIMARY_AMPLITUDE
    secondary = math.sin(x * 0.0017 + 1.4) * GROUND_SECONDARY_AMPLITUDE
    return GROUND_BASELINE + primary + secondary


def surface_from_pattern(pattern: Sequence[str], palette: dict[str, tuple[int, int, int]], pixel_size: int) -> pygame.Surface:
    if not pattern:
        raise ValueError("Pattern must contain at least one row.")
    row_length = len(pattern[0])
    surface = pygame.Surface((row_length * pixel_size, len(pattern) * pixel_size), pygame.SRCALPHA)
    for row_index, row in enumerate(pattern):
        if len(row) != row_length:
            raise ValueError("All pattern rows must have equal length.")
        for col_index, key in enumerate(row):
            color = palette.get(key)
            if not color:
                continue
            rect = pygame.Rect(
                col_index * pixel_size,
                row_index * pixel_size,
                pixel_size,
                pixel_size,
            )
            surface.fill(color, rect)
    return surface


def create_human_surface() -> pygame.Surface:
    surf = pygame.Surface((10, 24), pygame.SRCALPHA)
    pygame.draw.rect(surf, (60, 220, 80), pygame.Rect(3, 0, 4, 6))  # head
    pygame.draw.rect(surf, (230, 80, 210), pygame.Rect(2, 6, 6, 8))  # torso
    pygame.draw.rect(surf, (255, 160, 80), pygame.Rect(3, 14, 4, 8))  # legs
    return surf


def create_ship_body() -> pygame.Surface:
    surf = pygame.Surface((58, 20), pygame.SRCALPHA)
    pygame.draw.polygon(surf, (190, 190, 210), [(10, 9), (30, 2), (55, 9), (30, 14)])
    pygame.draw.polygon(surf, (150, 160, 200), [(14, 9), (30, 5), (46, 9), (30, 13)])
    pygame.draw.polygon(surf, (210, 70, 220), [(14, 11), (30, 15), (46, 15), (30, 13)])
    pygame.draw.rect(surf, (255, 255, 255), pygame.Rect(48, 8, 4, 3))
    pygame.draw.rect(surf, (255, 255, 200), pygame.Rect(52, 9, 3, 2))
    pygame.draw.rect(surf, (80, 200, 255), pygame.Rect(28, 6, 6, 3))
    pygame.draw.rect(surf, (40, 120, 255), pygame.Rect(28, 9, 6, 2))
    pygame.draw.rect(surf, (255, 120, 200), pygame.Rect(20, 11, 6, 2))
    pygame.draw.rect(surf, (255, 200, 80), pygame.Rect(18, 9, 4, 2))
    pygame.draw.rect(surf, (220, 120, 255), pygame.Rect(24, 13, 4, 2))
    pygame.draw.rect(surf, (130, 200, 255), pygame.Rect(36, 11, 4, 2))
    pygame.draw.rect(surf, (255, 255, 255), pygame.Rect(40, 7, 4, 2))
    pygame.draw.rect(surf, (200, 80, 220), pygame.Rect(14, 13, 4, 2))
    pygame.draw.rect(surf, (255, 80, 80), pygame.Rect(8, 10, 3, 4))
    pygame.draw.rect(surf, (255, 180, 60), pygame.Rect(6, 8, 3, 6))
    pygame.draw.rect(surf, (255, 255, 140), pygame.Rect(4, 9, 2, 4))
    pygame.draw.rect(surf, (80, 60, 60), pygame.Rect(0, 7, 6, 8))
    pygame.draw.rect(surf, (255, 255, 160), pygame.Rect(12, 6, 4, 3))
    pygame.draw.rect(surf, (90, 220, 160), pygame.Rect(44, 12, 4, 2))
    pygame.draw.rect(surf, (255, 255, 240), pygame.Rect(48, 12, 4, 2))
    return surf


def create_lander_surface(
    top_color: tuple[int, int, int] = LANDER_TOP_COLOR,
    body_color: tuple[int, int, int] = LANDER_BODY_COLOR,
    leg_color: tuple[int, int, int] = LANDER_LEG_COLOR,
    occupant_color: Optional[tuple[int, int, int]] = None,
) -> pygame.Surface:
    occupant = occupant_color if occupant_color else body_color
    outline = tuple(max(0, min(255, int(channel * 0.55))) for channel in body_color)
    pixel_pattern = [
        ".YYYYY.",
        "YYYYYYY",
        "YOGCGOY",
        "YGGGGGY",
        ".GCLCG.",
        ".L...L.",
        "L.....L",
    ]
    palette = {
        "Y": top_color,
        "G": body_color,
        "O": outline,
        "L": leg_color,
        "C": occupant,
    }
    return surface_from_pattern(pixel_pattern, palette, pixel_size=4)


def create_mutant_surface(colors: tuple[tuple[int, int, int], tuple[int, int, int]]) -> pygame.Surface:
    top_color, body_color = colors
    pixel_pattern = [
        ".YYYYY.",
        "YYYYYYY",
        "YOGMGOY",
        "YGGGGGY",
        ".GMLMG.",
        ".L...L.",
        "L.....L",
    ]
    outline = tuple(max(0, min(255, int(channel * 0.55))) for channel in body_color)
    palette = {
        "Y": top_color,
        "G": body_color,
        "O": outline,
        "L": (0, 200, 0),
        "M": CAPTURED_HUMAN_COLOR,
    }
    return surface_from_pattern(pixel_pattern, palette, pixel_size=4)


HUMAN_BASE_SURFACE = create_human_surface()
SHIP_BODY_SURFACE = create_ship_body()
SHIP_BODY_FLIPPED = pygame.transform.flip(SHIP_BODY_SURFACE, True, False)
LIFE_ICON_SURFACE = pygame.transform.scale(SHIP_BODY_SURFACE, (32, 14))
LANDER_BASE_SURFACE = create_lander_surface()
MUTANT_COLOR_ROTATION = [
    ((220, 255, 120), (0, 255, 0)),
    ((255, 240, 160), (40, 255, 120)),
    ((255, 220, 120), (0, 255, 160)),
    ((240, 255, 150), (60, 255, 80)),
]
EMBEDDED_HUMAN_SURFACE = pygame.transform.scale(HUMAN_BASE_SURFACE, (8, 16))
GROUND_ERUPTION_PARTICLE_COLORS = [
    (255, 200, 120),
    (255, 160, 200),
    (255, 240, 200),
    (255, 140, 80),
]
GROUND_ERUPTION_PARTICLE_COUNT = 180
GROUND_ERUPTION_TTL = 1.6


@dataclass
class Timer:
    time_left: float

    def update(self, dt: float) -> bool:
        self.time_left -= dt
        return self.time_left <= 0


# Sprite base classes -------------------------------------------------------------
class WorldSprite(pygame.sprite.Sprite):
    """Base sprite that tracks world-space position with horizontal wraparound."""

    def __init__(self):
        super().__init__()
        self.world_pos = pygame.math.Vector2(0, 0)
        self.velocity = pygame.math.Vector2(0, 0)
        # Each subclass must set image/rect.
        self.image: pygame.Surface
        self.rect: pygame.Rect

    def update(self, dt: float):
        """Advance the entire simulation by dt seconds."""
        self.world_pos += self.velocity * dt
        self.world_pos.x = wrap_position(self.world_pos.x)

    def update_rect(self, camera_x: float):
        self.rect.centerx = int(world_to_screen(self.world_pos.x, camera_x))
        self.rect.centery = int(self.world_pos.y)


class Laser(WorldSprite):
    """Player laser beam represented as a short-lived streak."""
    def __init__(
        self,
        x: float,
        y: float,
        velocity: pygame.math.Vector2,
        ttl: float = 0.45,
        *,
        colors: Optional[list[tuple[int, int, int]]] = None,
        length: int = 64,
        thickness: int = 4,
        anchor: str = "center",
        color_interval: float = 0.045,
    ):
        super().__init__()
        self.direction = 1 if velocity.x >= 0 else -1
        self.colors = colors or [
            (255, 235, 60),
            (255, 250, 140),
            (255, 255, 200),
            (255, 255, 255),
        ]
        self.base_length = max(6, length)
        self.thickness = max(2, thickness)
        self.anchor = anchor
        self.max_ttl = ttl
        self.ttl = ttl
        self.color_index = 0
        self.color_interval = color_interval
        self.color_timer = color_interval

        self.image = pygame.Surface((self.base_length, self.thickness), pygame.SRCALPHA)
        self.rect = self.image.get_rect()
        self.world_pos.update(x, y)
        self.velocity = velocity

        self.update_image()

    def update(self, dt: float):
        super().update(dt)
        self.ttl -= dt
        self.color_timer -= dt
        if self.color_timer <= 0:
            self.color_timer = self.color_interval
            self.color_index = (self.color_index + 1) % len(self.colors)
        if self.ttl <= 0:
            self.kill()
            return
        self.update_image()

    def update_rect(self, camera_x: float):
        if self.anchor == "tip":
            screen_x = world_to_screen(self.world_pos.x, camera_x)
            screen_y = int(self.world_pos.y)
            if self.direction >= 0:
                self.rect.midleft = (int(screen_x), screen_y)
            else:
                self.rect.midright = (int(screen_x), screen_y)
        else:
            super().update_rect(camera_x)

    def update_image(self):
        life = clamp(self.ttl / self.max_ttl, 0.0, 1.0)
        color = self.colors[self.color_index]
        alpha = int(70 + 185 * life)
        length = max(8, int(self.base_length * (0.15 + 0.85 * life)))
        start_x = 0 if self.direction >= 0 else self.base_length - length

        surface = pygame.Surface((self.base_length, self.thickness), pygame.SRCALPHA)
        core_rect = pygame.Rect(start_x, 0, length, self.thickness)
        pygame.draw.rect(surface, (*color, alpha), core_rect)

        inner_color = tuple(min(255, c + 50) for c in color)
        inner_height = max(1, self.thickness - 2)
        inner_rect = pygame.Rect(start_x, (self.thickness - inner_height) // 2, length, inner_height)
        pygame.draw.rect(surface, (*inner_color, min(255, alpha + 40)), inner_rect)

        tip_len = max(8, min(length // 6, 24))
        if self.direction >= 0:
            tip_rect = pygame.Rect(start_x + length - tip_len, 0, tip_len, self.thickness)
        else:
            tip_rect = pygame.Rect(start_x, 0, tip_len, self.thickness)
        pygame.draw.rect(surface, (255, 255, 255, min(255, alpha + 60)), tip_rect)

        # trailing flicker bands
        band_len = max(8, length // 5)
        for i in range(3):
            blend = 0.7 - i * 0.18
            band_color = tuple(clamp(int(c * blend + 255 * (1 - blend)), 0, 255) for c in color)
            if self.direction >= 0:
                bx = start_x + max(0, length - tip_len - (i + 1) * band_len)
            else:
                bx = start_x + i * band_len
            band_rect = pygame.Rect(bx, 0, band_len, self.thickness)
            pygame.draw.rect(surface, (*band_color, max(60, int(alpha * (0.65 - i * 0.1)))), band_rect)

        self.image = surface
        self.rect = self.image.get_rect()


class EnemyShot(WorldSprite):
    """Simple projectile fired by enemies towards the player."""
    def __init__(self, x: float, y: float, velocity: pygame.math.Vector2):
        super().__init__()
        self.world_pos.update(x, y)
        self.velocity = velocity
        self.ttl = 2.0
        self.frame_timer = 0.0
        self.frame_interval = 0.08
        self.frames = [self._make_frame(True), self._make_frame(False)]
        self.frame_index = 0
        self.image = self.frames[self.frame_index]
        self.rect = self.image.get_rect()

    def _make_frame(self, primary: bool) -> pygame.Surface:
        surf = pygame.Surface((12, 12), pygame.SRCALPHA)
        color = (255, 255, 160) if primary else (255, 200, 80)
        pygame.draw.rect(surf, color, pygame.Rect(1, 5, 10, 2))
        pygame.draw.rect(surf, color, pygame.Rect(5, 1, 2, 10))
        pygame.draw.rect(surf, (255, 255, 255), pygame.Rect(4, 4, 4, 4))
        return surf

    def update(self, dt: float):
        super().update(dt)
        self.ttl -= dt
        self.frame_timer += dt
        if self.frame_timer >= self.frame_interval:
            self.frame_timer -= self.frame_interval
            self.frame_index = (self.frame_index + 1) % len(self.frames)
            center = self.rect.center
            self.image = self.frames[self.frame_index]
            self.rect = self.image.get_rect()
            self.rect.center = center
        if self.ttl <= 0:
            self.kill()


class ScorePopup(WorldSprite):
    def __init__(self, x: float, y: float, text: str, colors: list[tuple[int, int, int]], font: pygame.font.Font):
        super().__init__()
        self.world_pos.update(x, y)
        self.velocity.update(0, -60)
        self.text = text
        self.colors = colors
        self.font = font
        self.color_index = 0
        self.color_interval = 0.12
        self.color_timer = self.color_interval
        self.life = 0.9
        self.ttl = self.life
        self.image = self.font.render(self.text, True, self.colors[self.color_index])
        self.image.set_alpha(255)
        self.rect = self.image.get_rect()

    def update(self, dt: float):
        super().update(dt)
        self.ttl -= dt
        self.color_timer -= dt
        if self.color_timer <= 0:
            self.color_timer = self.color_interval
            self.color_index = (self.color_index + 1) % len(self.colors)
        if self.ttl <= 0:
            self.kill()
            return
        alpha = clamp(int(255 * (self.ttl / self.life)), 40, 255)
        color = self.colors[self.color_index]
        self.image = self.font.render(self.text, True, color)
        self.image.set_alpha(alpha)
        self.rect = self.image.get_rect()


class GroundParticle(WorldSprite):
    def __init__(self, x: float, y: float):
        super().__init__()
        angle = random.uniform(-math.pi * 0.4, math.pi * 0.4)
        speed = random.uniform(160, 340)
        self.velocity.from_polar((speed, math.degrees(angle)))
        self.world_pos.update(x, y)
        size = random.randint(3, 6)
        self.image = pygame.Surface((size, size), pygame.SRCALPHA)
        color = random.choice(GROUND_ERUPTION_PARTICLE_COLORS)
        pygame.draw.rect(self.image, color, self.image.get_rect())
        self.rect = self.image.get_rect()
        self.ttl = GROUND_ERUPTION_TTL + random.uniform(-0.3, 0.3)

    def update(self, dt: float):
        super().update(dt)
        self.ttl -= dt
        self.velocity.y += 220 * dt
        if self.ttl <= 0:
            self.kill()


class HyperspaceFlash(WorldSprite):
    """Radial flash that accompanies the hyperspace charge-up."""
    def __init__(self, x: float, y: float, radius: float = 80.0, invert: bool = False):
        super().__init__()
        self.world_pos.update(x, y)
        size = int(radius * 2.2)
        self.image = pygame.Surface((size, size), pygame.SRCALPHA)
        for r in range(size // 2, 0, -4):
            alpha = int(255 * (r / (size / 2)))
            color = (255, 234, 160, alpha)
            pygame.draw.circle(self.image, color, (size // 2, size // 2), r)
        self.rect = self.image.get_rect(center=(0, 0))
        self.duration = 0.24
        self.ttl = self.duration
        self.invert = invert
        self._apply_alpha()

    def update(self, dt: float):
        self.ttl -= dt
        if self.ttl <= 0:
            self.kill()
        else:
            self._apply_alpha()

    def _apply_alpha(self):
        progress = clamp(1 - self.ttl / self.duration, 0.0, 1.0)
        if self.invert:
            alpha = int(255 * progress)
        else:
            alpha = int(255 * (1 - progress))
        self.image.set_alpha(alpha)


class HyperspaceFragment(WorldSprite):
    """Short-lived debris fragment used by legacy hyperspace FX."""
    def __init__(self, x: float, y: float, color: pygame.Color):
        super().__init__()
        self.world_pos.update(x, y)
        angle = random.uniform(0, math.tau)
        speed = random.uniform(300, 600)
        self.velocity.from_polar((speed, math.degrees(angle)))
        size = random.randint(2, 4)
        self.image = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.rect(self.image, color, pygame.Rect(0, 0, size, size))
        self.rect = self.image.get_rect()
        self.ttl = random.uniform(0.12, 0.18)

    def update(self, dt: float):
        super().update(dt)
        self.ttl -= dt
        self.velocity *= (1 - 6 * dt)
        if self.ttl <= 0:
            self.kill()


class HyperspaceAfterImage(WorldSprite):
    """Trailing ghost image rendered while the ship phases out."""
    def __init__(self, x: float, y: float, image: pygame.Surface):
        super().__init__()
        self.world_pos.update(x, y)
        self.image = pygame.transform.scale(image, (int(image.get_width() * 1.1), int(image.get_height() * 1.1)))
        self.image.set_alpha(180)
        self.rect = self.image.get_rect()
        self.ttl = 0.04

    def update(self, dt: float):
        super().update(dt)
        self.ttl -= dt
        if self.ttl <= 0:
            self.kill()
        else:
            alpha = int(180 * (self.ttl / 0.04))
            self.image.set_alpha(max(0, alpha))


class HyperspaceShard(WorldSprite):
    """Animates a ship fragment along a curved easing path between two points."""
    def __init__(
        self,
        start: pygame.math.Vector2,
        target: pygame.math.Vector2,
        duration: float,
        image: pygame.Surface,
        *,
        fade_in: bool,
        owner: Optional["Player"] = None,
        inward: bool = False,
    ):
        super().__init__()
        self.start = pygame.math.Vector2(start)
        self.target = pygame.math.Vector2(target)
        self.duration = max(0.01, duration)
        self.elapsed = 0.0
        self.fade_in = fade_in
        self.image = image.copy()
        self.rect = self.image.get_rect()
        self.world_pos.update(self.start.x, self.start.y)
        self.owner = owner
        self.inward = inward

    def update(self, dt: float):
        self.elapsed += dt
        progress = clamp(self.elapsed / self.duration, 0.0, 1.0)
        eased = 0.5 - 0.5 * math.cos(progress * math.pi)
        position = self.start.lerp(self.target, eased)
        self.world_pos.update(position.x, position.y)
        alpha_progress = progress if self.fade_in else (1 - progress)
        alpha = clamp(int(255 * alpha_progress), 0, 255)
        self.image.set_alpha(alpha)
        if self.elapsed >= self.duration:
            self.kill()
            if self.inward and self.owner:
                self.owner.notify_inbound_shard_complete()
class Human(WorldSprite):
    """Colonist logic covering abduction, falling, landing, and scoring."""
    def __init__(self, game: "DefenderGame", x: float):
        super().__init__()
        self.game = game
        self.base_image = HUMAN_BASE_SURFACE
        self.image = self.base_image.copy()
        self.rect = self.image.get_rect()
        ground = terrain_height(x)
        self.world_pos.update(x, ground - self.rect.height / 2)
        self.state = "ground"  # ground, captured, falling, dead, carried
        self.carrier: Optional[WorldSprite] = None
        self.velocity.update(0, 0)
        self.visible = True
        self.drop_start_y = self.world_pos.y
        self.safe_landing_rewarded = True
        self.reserved_by: Optional["Lander"] = None

    def update(self, dt: float):
        if self.state == "falling":
            self.velocity.y += GRAVITY * dt
            self.velocity.y = min(self.velocity.y, TERMINAL_VELOCITY)
            self.world_pos.y += self.velocity.y * dt
            ground = terrain_height(self.world_pos.x)
            if self.world_pos.y >= ground - self.rect.height / 2:
                self.world_pos.y = ground - self.rect.height / 2
                drop_height = max(0.0, ground - self.drop_start_y)
                full_span = SCREEN_HEIGHT - PLAYFIELD_TOP
                lethal_height = full_span * SAFE_LANDING_HEIGHT_RATIO
                catastrophic_height = full_span * 0.75
                if drop_height >= catastrophic_height:
                    self.state = "dead"
                    self.velocity.update(0, 0)
                    self.visible = False
                    if self.game:
                        self.game.explosion(self.world_pos.x, self.world_pos.y)
                elif drop_height > lethal_height:
                    self.state = "dead"
                    self.velocity.update(0, 0)
                    self.visible = False
                    if self.game:
                        self.game.spawn_colonist_crater(self.world_pos.x, self.world_pos.y)
                else:
                    self.state = "ground"
                    self.velocity.update(0, 0)
                    self.visible = True
                    if self.game:
                        self.game.colonist_safe_landing(self)
        elif self.state == "captured" and self.carrier:
            self.world_pos.x = self.carrier.world_pos.x
            offset = (self.carrier.rect.height / 2) + (self.rect.height / 2) - 4
            self.world_pos.y = self.carrier.world_pos.y + offset
        elif self.state == "carried" and self.carrier:
            self.world_pos.x = self.carrier.world_pos.x
            offset = (self.carrier.rect.height / 2) + (self.rect.height / 2) - 6
            self.world_pos.y = self.carrier.world_pos.y + offset
            self.velocity.update(0, 0)
        elif self.state == "carried":
            self.start_falling()

    def start_falling(self):
        self.state = "falling"
        self.carrier = None
        self.velocity.update(0, 0)
        self.visible = True
        self.drop_start_y = self.world_pos.y
        self.safe_landing_rewarded = False
        self.release_reservation()

    def die(self):
        if self.state == "dead":
            return
        carrier = self.carrier
        self.state = "dead"
        self.visible = False
        self.carrier = None
        self.velocity.update(0, 0)
        self.release_reservation()
        # Notify lander carrying this human so it can resume normal behavior.
        if carrier and hasattr(carrier, "on_captive_removed"):
            carrier.on_captive_removed()

    def capture(self, lander: "Lander"):
        if self.state == "ground":
            self.state = "captured"
            self.carrier = lander
            self.release_reservation(lander)

    def attach_to_player(self, player: "Player"):
        self.state = "carried"
        self.carrier = player
        self.velocity.update(0, 0)
        self.visible = True
        self.release_reservation()

    def place_on_ground(self):
        ground = terrain_height(self.world_pos.x)
        self.world_pos.y = ground - self.rect.height / 2
        self.velocity.update(0, 0)
        self.state = "ground"
        self.visible = True
        self.carrier = None
        self.release_reservation()

    def kill(self):
        self.die()

    def reserve_for_lander(self, lander: "Lander") -> bool:
        if self.state != "ground":
            return False
        if self.reserved_by not in (None, lander):
            return False
        self.reserved_by = lander
        return True

    def release_reservation(self, lander: Optional["Lander"] = None):
        if lander is None or self.reserved_by is lander:
            self.reserved_by = None


class Player(WorldSprite):
    """Handles player input, movement, combat, scoring, and hyperspace effects."""
    def __init__(self, game: "DefenderGame"):
        super().__init__()
        self.game = game
        self.base_images = {
            1: SHIP_BODY_SURFACE,
            -1: SHIP_BODY_FLIPPED,
        }
        self.direction = 1
        self.thruster_color_index = 0
        self.thruster_timer = 0.0
        self.image = self.base_images[self.direction].copy()
        self.rect = self.image.get_rect()
        self.exhaust_offsets = [(0, 8), (2, 6), (2, 10), (4, 8)]
        self.world_pos.update(WORLD_WIDTH / 2, PLAYFIELD_TOP + 180)
        self.fire_cooldown = 0.0
        self.lives = 2
        self.score = 0
        self.invulnerable = PLAYER_RESPAWN_INVULN
        self.held_human: Optional[Human] = None
        self.reverse_in_progress = False
        self.pending_direction = self.direction
        self.lead_duration = 1.35
        self.lead_timer = 0.0
        self.lead_animating = False
        self.lead_start = SCREEN_WIDTH * 0.25 * self.direction
        self.lead_target = self.lead_start
        self.lead_current = self.lead_start
        self.velocity_x = PLAYER_CRUISE_SPEED * self.direction
        self.pending_speed = abs(self.velocity_x)
        self.throttle_active = False
        self.opacity = 255
        self.render_visible = True
        self.demo_input: Optional[dict[int, bool]] = None
        self.controls_lock = 0.0
        self.hyperspace_state = "idle"
        self.hyperspace_timer = 0.0
        self.hyperspace_target: Optional[tuple[float, float]] = None
        self.hyperspace_attempts = 0
        self.afterimage_timer = 0.0
        self.update_image()
        self.lives_awarded = 0
        self.hyperspace_entry_direction = self.direction
        self.hyperspace_entry_lead = self.lead_current
        self.hyperspace_entry_velocity = self.velocity_x
        self.hyperspace_entry_pending = self.pending_speed
        self.hyperspace_entry_throttle = False

    def update(self, dt: float, pressed: Union[Iterable[bool], dict[int, bool]]):
        self.controls_lock = max(0.0, self.controls_lock - dt)
        input_vector = pygame.math.Vector2(0, 0)
        def is_down(key: int) -> bool:
            if isinstance(pressed, dict):
                return bool(pressed.get(key, False))
            return bool(pressed[key])

        if is_down(pygame.K_LEFT) or is_down(pygame.K_a):
            input_vector.x -= 1
        if is_down(pygame.K_RIGHT) or is_down(pygame.K_d):
            input_vector.x += 1
        if is_down(pygame.K_UP) or is_down(pygame.K_w):
            input_vector.y -= 1
        if is_down(pygame.K_DOWN) or is_down(pygame.K_s):
            input_vector.y += 1
        if input_vector.length_squared() > 0:
            input_vector = input_vector.normalize()

        if self.controls_lock > 0:
            input_vector.x = 0
            input_vector.y = 0

        desired_dir = 0
        if input_vector.x > 0.1:
            desired_dir = 1
        elif input_vector.x < -0.1:
            desired_dir = -1

        was_thruster = self.throttle_active

        if desired_dir and not self.reverse_in_progress and desired_dir != self.direction:
            self.begin_reverse_traverse(desired_dir)

        if self.reverse_in_progress:
            effective_vx = 0.0
            self.velocity_x = max(self.velocity_x - ENGINE_DAMPING * dt, PLAYER_CRUISE_SPEED * self.direction)
        else:
            if desired_dir:
                self.velocity_x += desired_dir * PLAYER_ACCEL * dt
            cruise = PLAYER_CRUISE_SPEED * (1 if self.velocity_x >= 0 else -1)
            if not desired_dir:
                if abs(self.velocity_x) > abs(cruise):
                    self.velocity_x -= ENGINE_DAMPING * dt * (1 if self.velocity_x > 0 else -1)
                    if abs(self.velocity_x) < abs(cruise):
                        self.velocity_x = cruise
                else:
                    self.velocity_x = cruise
            self.velocity_x = clamp(self.velocity_x, -PLAYER_MAX_SPEED, PLAYER_MAX_SPEED)
            if abs(self.velocity_x) > self.pending_speed:
                self.pending_speed = abs(self.velocity_x)
            effective_vx = self.velocity_x

        throttle = (not self.reverse_in_progress) and (desired_dir != 0)
        if throttle != was_thruster:
            if throttle:
                self.game.sfx.loop("engine")
            else:
                self.game.sfx.stop("engine")
        self.throttle_active = throttle
        if throttle != was_thruster:
            self.update_image()

        if self.lead_animating:
            self.lead_timer += dt
            progress = clamp(self.lead_timer / self.lead_duration, 0.0, 1.0)
            smooth = 0.5 - 0.5 * math.cos(math.pi * progress)
            self.lead_current = self.lead_start + (self.lead_target - self.lead_start) * smooth
            if progress >= 1.0:
                self.lead_animating = False
                self.lead_current = self.lead_target
                self.direction = self.pending_direction
                self.reverse_in_progress = False
                self.velocity_x = self.pending_speed * self.direction
                self.throttle_active = False
                self.update_image()
        else:
            self.lead_current = SCREEN_WIDTH * 0.25 * self.direction
            if desired_dir and desired_dir != self.direction:
                self.begin_reverse_traverse(desired_dir)

        if self.hyperspace_state != "idle":
            effective_vx = 0.0
            input_vector.y = 0.0

        self.world_pos.x = wrap_position(self.world_pos.x + effective_vx * dt)
        self.world_pos.y += input_vector.y * PLAYER_VERTICAL_SPEED * dt
        lower_bound = PLAYFIELD_TOP
        self.world_pos.y = clamp(self.world_pos.y, lower_bound, SCREEN_HEIGHT - 40)

        if self.throttle_active:
            self.thruster_timer -= dt
            if self.thruster_timer <= 0:
                self.thruster_timer = random.uniform(0.05, 0.12)
                self.thruster_color_index = random.randrange(len(THRUSTER_COLORS))
                self.update_image()
        else:
            self.thruster_timer = 0.0

        self.fire_cooldown -= dt
        if is_down(pygame.K_SPACE) and self.fire_cooldown <= 0:
            self.fire()
            self.fire_cooldown = PLAYER_FIRE_COOLDOWN

        if self.invulnerable > 0:
            self.invulnerable -= dt

        if self.held_human:
            self.held_human.attach_to_player(self)
            self.held_human.world_pos.x = wrap_position(self.world_pos.x)
            offset = (self.rect.height / 2) + (self.held_human.rect.height / 2) - 6
            self.held_human.world_pos.y = self.world_pos.y + offset

        self.update_hyperspace(dt)
        self.check_extra_life()

    def check_extra_life(self):
        if self.lives >= 5:
            return
        threshold = (self.lives_awarded + 1) * 10000
        if self.score >= threshold:
            self.lives += 1
            self.lives_awarded += 1

    def notify_inbound_shard_complete(self):
        """Called by inward shards as they finish so we know when to render the ship again."""
        self.hyperspace_inbound_shards = max(0, self.hyperspace_inbound_shards - 1)

    def fire(self):
        direction_vector = pygame.math.Vector2(self.direction, 0)
        bullet_velocity = direction_vector * PLAYER_BULLET_SPEED
        spawn_x = wrap_position(self.world_pos.x + self.direction * (self.rect.width / 2 - 2))
        beam_colors = [
            (255, 235, 60),
            (255, 250, 140),
            (255, 255, 210),
            (255, 255, 255),
        ]
        bullet = Laser(
            spawn_x,
            self.world_pos.y,
            bullet_velocity,
            ttl=0.48,
            colors=beam_colors,
            length=SCREEN_WIDTH,
            thickness=5,
            anchor="tip",
            color_interval=0.03,
        )
        self.game.lasers.add(bullet)
        self.game.all_sprites.add(bullet)
        self.game.sfx.play("player_fire")

    def hit(self):
        if self.game.no_death:
            self.invulnerable = max(self.invulnerable, 0.5)
            return
        if self.invulnerable > 0:
            return
        self.drop_carried_human(force_fall=True)
        self.game.spawn_player_explosion(self.world_pos.x, self.world_pos.y)
        self.game.begin_player_respawn_delay()

    def update_image(self):
        center = self.rect.center if self.rect else (0, 0)
        base = self.base_images[self.direction]
        self.image = base.copy()
        if self.throttle_active:
            if self.direction == 1:
                for index, (dx, dy) in enumerate(self.exhaust_offsets):
                    tint = THRUSTER_COLORS[(self.thruster_color_index + index) % len(THRUSTER_COLORS)]
                    self.image.fill(tint, pygame.Rect(dx, dy, 2, 2))
            else:
                for index, (dx, dy) in enumerate(self.exhaust_offsets):
                    mirror_x = self.image.get_width() - dx - 2
                    tint = THRUSTER_COLORS[(self.thruster_color_index + index) % len(THRUSTER_COLORS)]
                    self.image.fill(tint, pygame.Rect(mirror_x, dy, 2, 2))
        self.rect = self.image.get_rect()
        self.rect.center = center
        alpha = self.opacity if self.render_visible else 0
        self.image.set_alpha(alpha)

    def pickup_human(self, human: Human):
        if self.held_human:
            return
        self.held_human = human
        human.attach_to_player(self)

    def drop_carried_human(self, force_fall: bool = False):
        if not self.held_human:
            return
        human = self.held_human
        self.held_human = None
        if force_fall:
            human.world_pos.x = wrap_position(self.world_pos.x)
            human.world_pos.y = self.world_pos.y + self.rect.height
            human.start_falling()
        else:
            human.world_pos.x = wrap_position(self.world_pos.x)
            human.carrier = None
            human.start_falling()

    def deliver_human(self) -> Optional[Human]:
        if not self.held_human:
            return None
        human = self.held_human
        self.held_human = None
        human.world_pos.x = wrap_position(self.world_pos.x)
        human.carrier = None
        human.place_on_ground()
        return human

    def begin_reverse_traverse(self, target_direction: Optional[int] = None):
        if self.reverse_in_progress:
            return
        if target_direction is None:
            target_direction = -self.direction or -1
        if target_direction == self.direction:
            return
        self.reverse_in_progress = True
        self.pending_speed = max(abs(self.velocity_x), PLAYER_CRUISE_SPEED)
        self.velocity_x = 0.0
        self.pending_direction = target_direction
        self.lead_start = self.lead_current
        self.lead_target = SCREEN_WIDTH * 0.25 * target_direction
        self.lead_timer = 0.0
        self.lead_animating = True
        self.throttle_active = False
        self.game.sfx.stop("engine")

    def get_camera_lead(self) -> float:
        return self.lead_current

    # Hyperspace orchestrates a multi-phase animation where the ship shards fly outward,
    # the player jumps to a new location, and the shards fly back before control resumes.
    def start_hyperspace(self):
        if self.hyperspace_state != "idle" or self.game.hyperspace_cooldown > 0:
            return
        self.hyperspace_entry_direction = self.direction
        self.hyperspace_entry_lead = self.lead_current
        self.hyperspace_entry_velocity = self.velocity_x
        self.hyperspace_entry_pending = self.pending_speed
        self.hyperspace_entry_throttle = self.throttle_active
        self.hyperspace_inbound_shards = 0
        self.game.sfx.play("hyperspace_in")
        self.game.sfx.play("hyperspace_out")
        self.hyperspace_state = "vanish"
        self.hyperspace_timer = 0.0
        self.controls_lock = max(self.controls_lock, HYPERSPACE_LOCK_DURATION)
        self.throttle_active = False
        self.game.sfx.stop("engine")
        self.game.spawn_hyperspace_shards(self, outward=True)

    # The hyperspace state machine drives the vanish → jump → reappear → stabilize flow.
    # Visibility is suppressed until all returning shards notify completion.
    def update_hyperspace(self, dt: float):
        if self.hyperspace_state == "idle":
            if self.opacity < 255:
                self.opacity = min(255, self.opacity + int(800 * dt))
                self.update_image()
            return

        self.hyperspace_timer += dt

        if self.hyperspace_state == "vanish":
            progress = clamp(self.hyperspace_timer / HYPERSPACE_VANISH_TIME, 0.0, 1.0)
            new_opacity = int(255 * (1 - progress))
            if new_opacity != self.opacity:
                self.opacity = new_opacity
                self.update_image()
            if self.hyperspace_timer >= HYPERSPACE_VANISH_TIME:
                self.render_visible = False
                self.opacity = 0
                self.update_image()
                self.hyperspace_state = "jump"
                self.hyperspace_timer = 0.0
                self.game.perform_hyperspace_jump(self)
                self.velocity_x = 0.0
                self.pending_speed = 0.0
                self.throttle_active = False

        elif self.hyperspace_state == "jump":
            if self.hyperspace_timer >= HYPERSPACE_REAPPEAR_DELAY:
                self.hyperspace_state = "reappear"
                self.hyperspace_timer = 0.0
                self.game.spawn_hyperspace_shards(self, outward=False)
                self.game.sfx.play("hyperspace_out")

        elif self.hyperspace_state == "reappear":
            self.render_visible = False
            self.opacity = 0
            if self.hyperspace_timer >= HYPERSPACE_REAPPEAR_TIME and self.hyperspace_inbound_shards == 0:
                self.hyperspace_state = "stabilize"
                self.hyperspace_timer = 0.0
                self.direction = self.hyperspace_entry_direction
                self.update_image()

        elif self.hyperspace_state == "stabilize":
            if self.hyperspace_timer >= HYPERSPACE_STABILIZE_TIME:
                self.hyperspace_state = "idle"
                self.hyperspace_timer = 0.0
                self.render_visible = True
                self.opacity = 255
                self.update_image()
                self.velocity_x = self.hyperspace_entry_velocity
                self.pending_speed = max(abs(self.velocity_x), PLAYER_CRUISE_SPEED)
                self.throttle_active = self.hyperspace_entry_throttle
                if self.throttle_active:
                    self.game.sfx.loop("engine")
                self.game.hyperspace_cooldown = HYPERSPACE_COOLDOWN


class Enemy(WorldSprite):
    """Base enemy behaviour shared across all alien archetypes."""
    def __init__(self, game: "DefenderGame"):
        super().__init__()
        self.game = game
        self.health = 1
        self.points = 0
        self.fire_timer = random.uniform(*LANDER_FIRE_INTERVAL)

    def take_damage(self, amount: int):
        self.health -= amount
        if self.health <= 0:
            self.destroy()
            return True
        return False

    def destroy(self):
        self.kill()
        if self.game.player:
            self.game.player.score += self.points
        self.game.enemy_destroyed(self)


class Lander(Enemy):
    """Abducts colonists, mutates into mutants, and shoots at the player."""
    def __init__(self, game: "DefenderGame", x: float):
        super().__init__(game)
        self.base_image = LANDER_BASE_SURFACE
        self.image = self.base_image.copy()
        self.rect = self.image.get_rect()
        self.world_pos.update(x, random.uniform(PLAYFIELD_TOP + 40, PLAYFIELD_TOP + 160))
        self.home_altitude = self.world_pos.y
        self.patrol_direction = random.choice([-1, 1])
        self.target: Optional[Human] = None
        self.state = "patrolling"  # patrolling, descending, ascending
        self.health = 1
        self.points = 150
        self.fire_timer = random.uniform(*LANDER_FIRE_INTERVAL)

    def update(self, dt: float):
        super().update(dt)

        if self.target and self.target.state == "dead":
            self.on_captive_removed()

        if self.state == "patrolling":
            if self.target and (
                self.target.state != "ground"
                or self.target.carrier not in (None, self)
                or self.target.reserved_by not in (None, self)
            ):
                self.release_target()
            if not self.target:
                candidate = self.find_target()
                if candidate and candidate.reserve_for_lander(self):
                    self.target = candidate
            if self.target:
                direction = math.copysign(1, shortest_offset(self.target.world_pos.x, self.world_pos.x))
                self.world_pos.x = wrap_position(self.world_pos.x + direction * LANDER_SPEED * dt)
                if abs(shortest_offset(self.target.world_pos.x, self.world_pos.x)) < 6:
                    self.state = "descending"
            else:
                if random.random() < 0.02:
                    self.patrol_direction *= -1
                self.world_pos.x = wrap_position(
                    self.world_pos.x + self.patrol_direction * LANDER_SPEED * 0.4 * dt
                )
                target_altitude = clamp(self.home_altitude, PLAYFIELD_TOP + 40, PLAYFIELD_TOP + 160)
                delta = target_altitude - self.world_pos.y
                self.world_pos.y += clamp(delta, -abs(LANDER_DESCENT_SPEED * dt), abs(LANDER_ASCENT_SPEED * dt))
        elif self.state == "descending":
            self.world_pos.y += LANDER_DESCENT_SPEED * dt
            if self.target:
                hover = self.target.world_pos.y - (self.rect.height / 2 + self.target.rect.height / 2 - 6)
                if self.world_pos.y >= hover:
                    self.world_pos.y = hover
                    self.state = "ascending"
                    self.target.capture(self)
        elif self.state == "ascending":
            self.world_pos.y -= LANDER_ASCENT_SPEED * dt
            self.world_pos.x = wrap_position(self.world_pos.x + random.uniform(-40, 40) * dt)
            if self.world_pos.y <= max(LANDER_MIN_ALTITUDE, PLAYFIELD_TOP):
                self.mutate()
                return

        self.fire_timer -= dt
        if self.fire_timer <= 0:
            self.fire_timer = random.uniform(*LANDER_FIRE_INTERVAL)
            self.fire()

        self.update_image()

    def find_target(self) -> Optional[Human]:
        candidates = [
            h
            for h in self.game.humans
            if h.state == "ground" and h.carrier is None and h.reserved_by in (None, self)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda h: abs(shortest_offset(h.world_pos.x, self.world_pos.x)),
        )

    def fire(self):
        if not self.game.player:
            return
        to_player = pygame.math.Vector2(
            shortest_offset(self.game.player.world_pos.x, self.world_pos.x),
            self.game.player.world_pos.y - self.world_pos.y,
        )
        if to_player.length_squared() == 0:
            return
        direction = to_player.normalize()
        shot = EnemyShot(
            self.world_pos.x,
            self.world_pos.y,
            direction * LANDER_SHOT_SPEED,
        )
        self.game.enemy_shots.add(shot)
        self.game.all_sprites.add(shot)
        self.game.sfx.play("enemy_fire")

    def mutate(self):
        if self.target:
            self.target.kill()
        mutant = Mutant(self.game, self.world_pos.x, self.world_pos.y)
        self.kill()
        self.game.spawned_mutant(mutant)
        self.game.sfx.play("mutate")

    def destroy(self):
        if self.target and self.target.state == "captured":
            self.target.start_falling()
            if self.game.player:
                self.game.player.score += 350
        self.release_target()
        super().destroy()

    def update_image(self):
        self.image = self.base_image.copy()

    def release_target(self):
        if self.target:
            self.target.release_reservation(self)
        self.target = None

    def on_captive_removed(self):
        self.release_target()
        if self.state in ("descending", "ascending"):
            self.state = "patrolling"
        self.home_altitude = clamp(self.world_pos.y, PLAYFIELD_TOP + 40, PLAYFIELD_TOP + 160)
        self.patrol_direction = random.choice([-1, 1])


class Mutant(Enemy):
    def __init__(self, game: "DefenderGame", x: float, y: float):
        super().__init__(game)
        self.palette_index = random.randrange(len(MUTANT_COLOR_ROTATION))
        self.palette_timer = 0.0
        self.base_image = create_mutant_surface(MUTANT_COLOR_ROTATION[self.palette_index])
        self.image = self.base_image.copy()
        self.rect = self.image.get_rect()
        self.world_pos.update(x, y)
        self.health = 2
        self.points = 300
        self.fire_timer = random.uniform(*MUTANT_FIRE_INTERVAL)
        self.update_image()

    def update(self, dt: float):
        super().update(dt)
        if not self.game.player:
            return
        to_player = pygame.math.Vector2(
            shortest_offset(self.game.player.world_pos.x, self.world_pos.x),
            self.game.player.world_pos.y - self.world_pos.y,
        )
        if to_player.length_squared() > 0:
            direction = to_player.normalize()
            self.world_pos.x = wrap_position(self.world_pos.x + direction.x * MUTANT_SPEED * dt)
            self.world_pos.y += direction.y * MUTANT_SPEED * dt
            self.world_pos.y = clamp(self.world_pos.y, PLAYFIELD_TOP + 20, SCREEN_HEIGHT - 80)

        self.fire_timer -= dt
        if self.fire_timer <= 0:
            self.fire_timer = random.uniform(*MUTANT_FIRE_INTERVAL)
            self.fire()

        self.palette_timer -= dt
        if self.palette_timer <= 0:
            self.palette_timer = 0.12
            self.palette_index = (self.palette_index + 1) % len(MUTANT_COLOR_ROTATION)
            self.update_image()

    def fire(self):
        to_player = pygame.math.Vector2(
            shortest_offset(self.game.player.world_pos.x, self.world_pos.x),
            self.game.player.world_pos.y - self.world_pos.y,
        )
        if to_player.length_squared() == 0:
            return
        direction = to_player.normalize()
        shot = EnemyShot(
            self.world_pos.x,
            self.world_pos.y,
            direction * MUTANT_SHOT_SPEED,
        )
        self.game.enemy_shots.add(shot)
        self.game.all_sprites.add(shot)
        self.game.sfx.play("enemy_fire")

    def embed_human(self):
        pass

    def update_image(self):
        self.base_image = create_mutant_surface(MUTANT_COLOR_ROTATION[self.palette_index])
        center = self.rect.center if hasattr(self, "rect") else (0, 0)
        self.image = self.base_image.copy()
        self.rect = self.image.get_rect()
        self.rect.center = center


class Mine(WorldSprite):
    def __init__(self, game: "DefenderGame", x: float, y: float):
        super().__init__()
        self.game = game
        self.world_pos.update(x, y)
        self.velocity.update(0, 0)
        self.image = pygame.Surface((12, 12), pygame.SRCALPHA)
        pygame.draw.rect(self.image, (255, 220, 40), pygame.Rect(0, 5, 12, 2))
        pygame.draw.rect(self.image, (255, 220, 40), pygame.Rect(5, 0, 2, 12))
        pygame.draw.rect(self.image, (255, 255, 255), pygame.Rect(3, 3, 6, 6))
        self.rect = self.image.get_rect()
        self.ttl = MINE_TTL

    def update(self, dt: float):
        super().update(dt)
        self.ttl -= dt
        if self.ttl <= 0:
            self.kill()


class Bomber(Enemy):
    """Horizontally drifting bomber that drops explosive mines."""
    def __init__(self, game: "DefenderGame", x: float):
        super().__init__(game)
        pixel_pattern = [
            "OOOO",
            "OYYO",
            "OYYO",
            "OOOO",
        ]
        palette = {
            "O": (255, 153, 0),
            "Y": (255, 255, 0),
        }
        self.image = surface_from_pattern(pixel_pattern, palette, pixel_size=6)
        self.rect = self.image.get_rect()
        self.world_pos.update(x, random.uniform(PLAYFIELD_TOP + 80, PLAYFIELD_TOP + 180))
        self.direction = random.choice([-1, 1])
        self.drop_timer = random.uniform(*BOMBER_DROP_INTERVAL)
        self.points = 250

    def update(self, dt: float):
        super().update(dt)
        self.world_pos.x = wrap_position(self.world_pos.x + self.direction * BOMBER_SPEED * dt)
        oscillation = math.sin(pygame.time.get_ticks() * 0.002) * 20 * dt
        self.world_pos.y = clamp(self.world_pos.y + oscillation, PLAYFIELD_TOP + 60, SCREEN_HEIGHT - 140)
        self.drop_timer -= dt
        if self.drop_timer <= 0:
            self.drop_timer = random.uniform(*BOMBER_DROP_INTERVAL)
            self.game.spawn_mine(self.world_pos.x, self.world_pos.y + 20)


class Pod(Enemy):
    """Drifting energy pod that bursts into swarmer drones when destroyed."""
    def __init__(self, game: "DefenderGame", x: float):
        super().__init__(game)
        pixel_pattern = [
            "...B...",
            "..BMB..",
            ".YMMMY.",
            "RMMYMMR",
            ".YMMMY.",
            "..RMR..",
            "...R...",
        ]
        palette = {
            "M": (255, 0, 200),
            "B": (0, 204, 255),
            "Y": (255, 255, 0),
            "R": (255, 51, 0),
        }
        self.image = surface_from_pattern(pixel_pattern, palette, pixel_size=4)
        self.rect = self.image.get_rect()
        self.world_pos.update(x, random.uniform(PLAYFIELD_TOP + 100, PLAYFIELD_TOP + 220))
        self.velocity.update(random.choice([-1, 1]) * POD_SPEED, 0)
        self.points = 500

    def update(self, dt: float):
        super().update(dt)
        self.world_pos.x = wrap_position(self.world_pos.x + self.velocity.x * dt)
        if random.random() < 0.01:
            self.velocity.x *= -1
        vertical_offset = math.sin(pygame.time.get_ticks() * 0.002 + self.world_pos.x * 0.01) * POD_VERTICAL_RANGE * dt
        self.world_pos.y = clamp(self.world_pos.y + vertical_offset, PLAYFIELD_TOP + 80, PLAYFIELD_TOP + 240)

    def destroy(self):
        swarm_count = random.randint(*POD_SWARMER_COUNT)
        for _ in range(swarm_count):
            offset_x = random.uniform(-80, 80)
            offset_y = random.uniform(-60, 60)
            spawn_x = wrap_position(self.world_pos.x + offset_x)
            spawn_y = clamp(self.world_pos.y + offset_y, PLAYFIELD_TOP + 20, SCREEN_HEIGHT - 140)
            self.game.spawn_swarmer(spawn_x, spawn_y)
        super().destroy()


class Swarmer(Enemy):
    """Aggressive drone spawned from pods that homes in on the player."""
    def __init__(self, game: "DefenderGame", x: float, y: float):
        super().__init__(game)
        pixel_pattern = [
            ".R.",
            "RRR",
            "RFR",
            "R.R",
        ]
        palette = {
            "R": (255, 0, 0),
            "F": (255, 102, 0),
        }
        self.image = surface_from_pattern(pixel_pattern, palette, pixel_size=4)
        self.rect = self.image.get_rect()
        self.world_pos.update(x, y)
        self.points = 150
        self.fire_timer = 9999

    def update(self, dt: float):
        super().update(dt)
        if not self.game.player:
            return
        to_player = pygame.math.Vector2(
            shortest_offset(self.game.player.world_pos.x, self.world_pos.x),
            self.game.player.world_pos.y - self.world_pos.y,
        )
        if to_player.length_squared() > 0:
            direction = to_player.normalize()
            self.world_pos.x = wrap_position(self.world_pos.x + direction.x * SWARMER_SPEED * dt)
            self.world_pos.y += direction.y * SWARMER_SPEED * dt
        self.world_pos.y = clamp(self.world_pos.y, PLAYFIELD_TOP + 20, SCREEN_HEIGHT - 140)
        self.world_pos.x = wrap_position(self.world_pos.x + random.uniform(-SWARMER_JITTER, SWARMER_JITTER) * dt)


class Baiter(Enemy):
    """Fast hunter that spawns when the player stalls, keeping pressure high."""
    def __init__(self, game: "DefenderGame", x: float):
        super().__init__(game)
        pixel_pattern = [
            ".DGGGD.",
            "DGGGGGD",
            "GGYYYYG",
            ".DGGGD.",
        ]
        body_color = (0, 255, 0)
        outline_color = (0, 120, 0)
        palette = {
            "D": outline_color,
            "G": body_color,
            "Y": (255, 255, 51),
        }
        self.image = surface_from_pattern(pixel_pattern, palette, pixel_size=4)
        self.rect = self.image.get_rect()
        self.world_pos.update(x, random.uniform(PLAYFIELD_TOP + 120, PLAYFIELD_TOP + 200))
        self.fire_timer = random.uniform(*BAITER_FIRE_INTERVAL)
        self.points = 750

    def update(self, dt: float):
        super().update(dt)
        if not self.game.player:
            return
        to_player = pygame.math.Vector2(
            shortest_offset(self.game.player.world_pos.x, self.world_pos.x),
            self.game.player.world_pos.y - self.world_pos.y,
        )
        if to_player.length_squared() > 0:
            direction = to_player.normalize()
            self.world_pos.x = wrap_position(self.world_pos.x + direction.x * BAITER_SPEED * dt)
            self.world_pos.y += direction.y * BAITER_SPEED * dt
        self.world_pos.y = clamp(self.world_pos.y, PLAYFIELD_TOP + 40, SCREEN_HEIGHT - 140)

        self.fire_timer -= dt
        if self.fire_timer <= 0:
            self.fire_timer = random.uniform(*BAITER_FIRE_INTERVAL)
            self.fire()

    def fire(self):
        if not self.game.player:
            return
        direction = pygame.math.Vector2(
            shortest_offset(self.game.player.world_pos.x, self.world_pos.x),
            self.game.player.world_pos.y - self.world_pos.y,
        )
        if direction.length_squared() == 0:
            return
        bullet = EnemyShot(
            self.world_pos.x,
            self.world_pos.y,
            direction.normalize() * MUTANT_SHOT_SPEED,
        )
        self.game.enemy_shots.add(bullet)
        self.game.all_sprites.add(bullet)
        self.game.sfx.play("enemy_fire")


# Background starfield -----------------------------------------------------------
class StarField:
    def __init__(self):
        self.layers = []
        for layer in range(STAR_LAYERS):
            layer_speed = 20 + layer * 40
            stars = [
                (random.uniform(0, WORLD_WIDTH), random.uniform(0, SCREEN_HEIGHT), layer_speed)
                for _ in range(STARS_PER_LAYER)
            ]
            self.layers.append(stars)

    def draw(self, surface: pygame.Surface, camera_x: float):
        for layer_index, stars in enumerate(self.layers):
            color = STAR_COLORS[layer_index % len(STAR_COLORS)]
            for sx, sy, speed in stars:
                screen_x = world_to_screen(sx, camera_x * (speed / 80.0))
                if -4 <= screen_x <= SCREEN_WIDTH + 4:
                    surface.fill(color, pygame.Rect(int(screen_x), int(sy), 2, 2))


# Main game controller -----------------------------------------------------------
class DefenderGame:
    """High-level game controller managing state, entities, rendering, and input."""
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.starfield = StarField()
        self.all_sprites = pygame.sprite.Group()
        self.enemies = pygame.sprite.Group()
        self.lasers = pygame.sprite.Group()
        self.enemy_shots = pygame.sprite.Group()
        self.humans = pygame.sprite.Group()
        self.player: Optional[Player] = None
        self.spawn_timer = LANDER_SPAWN_INTERVAL
        self.state = "playing"
        self.message_timer: Optional[Timer] = None
        self.camera_x = 0.0
        self.font = pygame.font.SysFont("Consolas", 20)
        self.big_font = pygame.font.SysFont("Consolas", 42, bold=True)
        self.popup_font = pygame.font.SysFont("Consolas", 18, bold=True)
        self.scanner_font = pygame.font.SysFont("Consolas", 16)
        self.no_death = False
        self.ground_destroyed = False
        self.wave = 1
        self.wave_message: Optional[str] = None
        self.total_wave_aliens = 0
        self.remaining_aliens = 0
        self.wave_timer = 0.0
        self.baiter_spawned = False
        self.sfx = SoundManager()
        self.pending_spawns: list[tuple[float, int, Callable, tuple]] = []
        self.smart_bombs = 0
        self.hyperspace_cooldown = 0.0
        self.radar_blink_timer = 0.0
        self.radar_warning = False
        self.radar_ground_destroyed = False
        self.spawn_sequence = 0
        self.demo_active = False
        self.demo_stage: Optional[str] = None
        self.demo_stage_timer = 0.0
        self.demo_target_lander: Optional["Lander"] = None
        self.demo_target_human: Optional[Human] = None
        self.demo_mutant_observed = False
        self.demo_prev_no_death = False
        self.demo_sound_enabled = self.sfx.enabled
        self.state = "title"
        self.title_timer = 0.0
        self.demo_duration = 15.0
        self.setup_world()
        self.respawn_timer: Optional[Timer] = None

    def setup_world(self):
        self.all_sprites.empty()
        self.enemies.empty()
        self.lasers.empty()
        self.enemy_shots.empty()
        self.humans.empty()
        self.repopulate_humans()
        self.player = Player(self)
        self.all_sprites.add(self.player)
        self.wave = 1
        self.total_wave_aliens = 0
        self.remaining_aliens = 0
        if self.state == "playing":
            self.start_wave(initial=True)
        self.ground_destroyed = False

    def repopulate_humans(self):
        for human in list(self.humans):
            self.all_sprites.remove(human)
        self.humans.empty()
        for x in HUMAN_POSITIONS:
            human = Human(self, x)
            self.humans.add(human)
            self.all_sprites.add(human)

    def set_message(self, text: str, duration: float = 3.0):
        self.wave_message = text
        self.message_timer = Timer(duration)

    def wave_composition(self) -> dict[str, int]:
        if self.wave == 1:
            return {"landers": 10, "bombers": 0, "pods": 0, "mutants": 0, "swarmer": 0, "baiters": 0}
        if self.wave == 2:
            return {"landers": 12, "bombers": 2, "pods": 0, "mutants": 0, "swarmer": 0, "baiters": 0}
        if self.wave == 3:
            return {"landers": 14, "bombers": 3, "pods": 0, "mutants": 0, "swarmer": 0, "baiters": 0}
        if self.wave == 4:
            return {"landers": 16, "bombers": 4, "pods": 0, "mutants": 0, "swarmer": 0, "baiters": 0}
        if self.wave == 5:
            return {"landers": 18, "bombers": 5, "pods": 3, "mutants": 0, "swarmer": 0, "baiters": 0}

        bonus = self.wave - 5
        landers = min(24, 18 + bonus)
        bombers = 5 + (bonus // 2)
        pods = 3 + max(0, (bonus - 1) // 2)
        swarmers = 0  # generated from pods when destroyed
        return {
            "landers": landers,
            "bombers": bombers,
            "pods": pods,
            "mutants": 0,
            "swarmer": swarmers,
            "baiters": 0,
        }

    def spawn_wave_enemies(self):
        self.remaining_aliens = 0
        self.total_wave_aliens = 0
        composition = self.wave_composition()
        self.pending_spawns.clear()

        def random_positions(count: int) -> list[float]:
            if count <= 0:
                return []
            spacing = WORLD_WIDTH / count
            return [(i + random.random()) * spacing % WORLD_WIDTH for i in range(count)]

        spawn_plan = (
            ("landers", self.spawn_lander, 0.5, 1.0),
            ("bombers", self.spawn_bomber, 12.0 if self.wave < 6 else 8.0, 3.0),
            ("pods", self.spawn_pod, 24.0, 3.8),
        )
        for category, func, start, gap in spawn_plan:
            count = composition.get(category, 0)
            if count <= 0:
                continue
            for x in random_positions(count):
                self.queue_spawn(start, func, x)
                start += gap

    def spawn_mutant_direct(self, x: float):
        mutant = Mutant(self, x, random.uniform(PLAYFIELD_TOP + 120, PLAYFIELD_TOP + 220))
        self.spawned_mutant(mutant)

    def start_wave(self, initial: bool = False):
        if self.player:
            self.player.held_human = None
            self.player.reverse_in_progress = False
            self.player.lead_animating = False
            self.player.pending_direction = self.player.direction
            lead = SCREEN_WIDTH * 0.25 * self.player.direction
            self.player.lead_current = lead
            self.player.lead_start = lead
            self.player.lead_target = lead
            self.player.lead_timer = 0.0
            self.player.velocity_x = PLAYER_CRUISE_SPEED * self.player.direction
            self.player.pending_speed = abs(self.player.velocity_x)
            self.player.throttle_active = False
            self.player.hyperspace_state = "idle"
            self.player.hyperspace_timer = 0.0
            self.player.controls_lock = 0.0
            self.player.render_visible = True
            self.player.opacity = 255
            self.sfx.stop("engine")
        self.wave_timer = 0.0
        self.baiter_spawned = False
        self.spawn_wave_enemies()
        self.ground_destroyed = False
        self.radar_ground_destroyed = False
        if initial:
            self.set_message(DEFAULT_HINT, 4.0)
        else:
            self.set_message(f"Wave {self.wave}", 3.0)
        self.smart_bombs = 1
        self.hyperspace_cooldown = 0.0

    def clear_wave_state(self):
        for projectile in list(self.lasers):
            projectile.kill()
        for projectile in list(self.enemy_shots):
            projectile.kill()
        if self.player:
            if self.player.held_human:
                self.player.held_human = None
            self.player.invulnerable = max(self.player.invulnerable, 1.0)
        self.remaining_aliens = 0
        self.baiter_spawned = False
        self.pending_spawns.clear()
        self.spawn_sequence = 0

    def begin_next_wave(self):
        self.wave += 1
        self.clear_wave_state()
        self.repopulate_humans()
        self.start_wave()

    def enemy_destroyed(self, enemy: Enemy):
        self.remaining_aliens = max(0, self.remaining_aliens - 1)

    def register_enemy_spawn(self):
        self.remaining_aliens += 1
        self.total_wave_aliens += 1

    def queue_spawn(self, delay: float, func: Callable, *args):
        self.spawn_sequence += 1
        spawn_time = self.wave_timer + delay
        heapq.heappush(self.pending_spawns, (spawn_time, self.spawn_sequence, func, args))

    def spawn_lander(self, x: float):
        lander = Lander(self, x)
        self.enemies.add(lander)
        self.all_sprites.add(lander)
        self.register_enemy_spawn()

    def spawn_bomber(self, x: float):
        bomber = Bomber(self, x)
        self.enemies.add(bomber)
        self.all_sprites.add(bomber)
        self.register_enemy_spawn()

    def spawn_pod(self, x: float):
        pod = Pod(self, x)
        self.enemies.add(pod)
        self.all_sprites.add(pod)
        self.register_enemy_spawn()

    def spawn_swarmer(self, x: float, y: float):
        swarmer = Swarmer(self, x, y)
        self.enemies.add(swarmer)
        self.all_sprites.add(swarmer)
        self.register_enemy_spawn()

    def spawn_baiter(self):
        baiter_x = self.player.world_pos.x if self.player else WORLD_WIDTH / 2
        baiter = Baiter(self, wrap_position(baiter_x + WORLD_WIDTH / 2 * random.choice([-1, 1])))
        self.enemies.add(baiter)
        self.all_sprites.add(baiter)
        self.register_enemy_spawn()
        self.baiter_spawned = True
        self.sfx.play("baiter")

    def spawn_mine(self, x: float, y: float):
        mine = Mine(self, x, y)
        self.enemy_shots.add(mine)
        self.all_sprites.add(mine)
        self.sfx.play("mine")
    def spawn_hyperspace_flash(self, x: float, y: float, invert: bool = False):
        flash = HyperspaceFlash(x, y, invert=invert)
        self.all_sprites.add(flash)

    def spawn_hyperspace_shatter(self, player: Player):
        base = player.base_images[player.hyperspace_entry_direction]
        width, height = base.get_size()
        colors = []
        for _ in range(120):
            px, py = random.randint(0, width - 1), random.randint(0, height - 1)
            color = base.get_at((px, py))
            if color.a > 0:
                colors.append(color)
        for color in colors:
            fragment = HyperspaceFragment(player.world_pos.x, player.world_pos.y, color)
            self.all_sprites.add(fragment)

    def spawn_hyperspace_afterimages(self, player: Player):
        for i in range(1, 4):
            offset = pygame.math.Vector2(-player.direction * i * 12, -i * 4)
            image = player.base_images[player.direction]
            ghost = HyperspaceAfterImage(player.world_pos.x + offset.x, player.world_pos.y + offset.y, image)
            self.all_sprites.add(ghost)

    # Slice the ship into an 8-piece grid (corners + edge centers) and animate the shards.
    # When outward=True the pieces blow apart; when False they converge and notify the player.
    def spawn_hyperspace_shards(self, player: Player, outward: bool):
        base = player.base_images[player.hyperspace_entry_direction]
        base_width, base_height = base.get_size()
        third_w = [base_width // 3, base_width // 3, base_width - 2 * (base_width // 3)]
        third_h = [base_height // 3, base_height // 3, base_height - 2 * (base_height // 3)]

        x_offsets = [0, third_w[0], third_w[0] + third_w[1]]
        y_offsets = [0, third_h[0], third_h[0] + third_h[1]]

        entry_pos = pygame.math.Vector2(player.world_pos.x, player.world_pos.y)
        center = entry_pos
        extent = max(SCREEN_WIDTH, SCREEN_HEIGHT) * 0.9
        duration = 1.35

        if outward:
            player.hyperspace_inbound_shards = 0

        shards_created = 0
        for row in range(3):
            for col in range(3):
                if row == 1 and col == 1:
                    continue  # skip center
                width = third_w[col]
                height = third_h[row]
                if width <= 0 or height <= 0:
                    continue
                rect = pygame.Rect(x_offsets[col], y_offsets[row], width, height)
                piece_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                piece_surface.blit(base, (0, 0), rect)
                offset = pygame.math.Vector2(rect.centerx - base_width / 2, rect.centery - base_height / 2)
                direction = pygame.math.Vector2(col - 1, row - 1)
                if direction.length_squared() == 0:
                    continue
                direction = direction.normalize()
                start = center + offset
                target = start + direction * extent
                if not outward:
                    start, target = target, start
                shard = HyperspaceShard(
                    start,
                    target,
                    duration,
                    piece_surface,
                    fade_in=not outward,
                    owner=player,
                    inward=not outward,
                )
                self.all_sprites.add(shard)
                shards_created += 1

        if not outward:
            player.hyperspace_inbound_shards = shards_created

    def is_hyperspace_safe(self, x: float, y: float) -> bool:
        terrain = terrain_height(x)
        if y < terrain + 60 or y > SCREEN_HEIGHT - 80:
            return False
        for enemy in self.enemies:
            if abs(shortest_offset(enemy.world_pos.x, x)) < 80 and abs(enemy.world_pos.y - y) < 80:
                return False
        for mine in self.enemy_shots:
            if isinstance(mine, Mine):
                if abs(shortest_offset(mine.world_pos.x, x)) < 70 and abs(mine.world_pos.y - y) < 70:
                    return False
        return True

    def perform_hyperspace_jump(self, player: Player):
        attempts = 0
        destination = (player.world_pos.x, player.world_pos.y)
        safe = False
        while attempts < 3:
            attempts += 1
            candidate = (
                random.uniform(0, WORLD_WIDTH),
                random.uniform(PLAYFIELD_TOP + 80, SCREEN_HEIGHT - 160),
            )
            if self.is_hyperspace_safe(*candidate):
                destination = candidate
                safe = True
                break
        if not safe:
            destination = (
                random.uniform(0, WORLD_WIDTH),
                random.uniform(PLAYFIELD_TOP + 80, SCREEN_HEIGHT - 160),
            )
        player.world_pos.update(*destination)
        player.direction = player.hyperspace_entry_direction
        player.velocity_x = PLAYER_CRUISE_SPEED * player.direction
        player.pending_speed = abs(player.velocity_x)
        player.controls_lock = max(player.controls_lock, HYPERSPACE_LOCK_DURATION - HYPERSPACE_VANISH_TIME)
        self.radar_blink_timer = 0.16
        self.radar_warning = not safe
        if not safe:
            player.hit()
        self.sfx.play("hyperspace_out")
        player.lead_current = player.hyperspace_entry_lead
        player.lead_start = player.hyperspace_entry_lead
        player.lead_target = player.hyperspace_entry_lead
        player.lead_animating = False

    def activate_smart_bomb(self):
        if self.smart_bombs <= 0 or not self.player:
            return
        self.smart_bombs -= 1
        self.sfx.play("smart_bomb")
        camera = self.camera_x
        for enemy in list(self.enemies):
            screen_x = world_to_screen(enemy.world_pos.x, camera)
            if -enemy.rect.width <= screen_x <= SCREEN_WIDTH + enemy.rect.width:
                self.explosion(enemy.world_pos.x, enemy.world_pos.y)
                enemy.take_damage(enemy.health)
        for projectile in list(self.enemy_shots):
            if isinstance(projectile, Mine):
                screen_x = world_to_screen(projectile.world_pos.x, camera)
                if -12 <= screen_x <= SCREEN_WIDTH + 12:
                    projectile.kill()

    def activate_hyperspace(self):
        if self.player:
            self.player.start_hyperspace()

    def spawned_mutant(self, mutant: Mutant):
        self.enemies.add(mutant)
        self.all_sprites.add(mutant)
        self.register_enemy_spawn()
        if self.demo_active:
            self.demo_mutant_observed = True

    def respawn_player(self):
        if not self.player:
            return
        if self.player.held_human:
            self.player.drop_carried_human(force_fall=True)
        self.player.world_pos.update(WORLD_WIDTH / 2, SCREEN_HEIGHT / 2)
        self.player.invulnerable = PLAYER_RESPAWN_INVULN
        self.player.direction = 1
        self.player.thruster_color_index = 0
        self.player.reverse_in_progress = False
        self.player.lead_animating = False
        self.player.pending_direction = self.player.direction
        lead = SCREEN_WIDTH * 0.25 * self.player.direction
        self.player.lead_current = lead
        self.player.lead_start = lead
        self.player.lead_target = lead
        self.player.lead_timer = 0.0
        self.player.velocity_x = PLAYER_CRUISE_SPEED * self.player.direction
        self.player.pending_speed = abs(self.player.velocity_x)
        self.player.throttle_active = False
        self.sfx.stop("engine")
        self.player.update_image()

    def game_over(self):
        self.state = "game_over"
        self.message_timer = None
        self.sfx.stop("engine")

    def update(self, dt: float):
        pressed = pygame.key.get_pressed()

        if self.state == "title":
            self.title_timer += dt
            if not self.demo_active and self.title_timer >= self.demo_duration:
                self.start_demo()
            if self.state == "title":
                return

        if self.respawn_timer and self.respawn_timer.update(dt):
            self.respawn_timer = None
            self.finish_player_respawn()

        if self.state == "demo":
            self.update_demo(dt)
            input_source = self.player.demo_input if self.player and self.player.demo_input else self.demo_blank_input()
        elif self.state != "playing":
            return
        else:
            input_source = pressed

        if self.player:
            self.player.update(dt, input_source)
            lead = self.player.get_camera_lead()
            self.camera_x = wrap_position(self.player.world_pos.x + lead)
            self.player.check_extra_life()

        if self.hyperspace_cooldown > 0:
            self.hyperspace_cooldown = max(0.0, self.hyperspace_cooldown - dt)

        # Update sprites.
        for sprite in list(self.all_sprites):
            if isinstance(sprite, Player):
                continue
            sprite.update(dt)

        # Refresh draw rectangles ahead of collision tests.
        for sprite in self.all_sprites:
            sprite.update_rect(self.camera_x)

        self.wave_timer += dt
        while self.pending_spawns and self.pending_spawns[0][0] <= self.wave_timer:
            _, _, func, args = heapq.heappop(self.pending_spawns)
            func(*args)

        if self.radar_blink_timer > 0:
            self.radar_blink_timer = max(0.0, self.radar_blink_timer - dt)

        if not self.baiter_spawned and self.wave_timer >= BAITER_SPAWN_DELAY:
            existing_baiter = any(isinstance(enemy, Baiter) for enemy in self.enemies)
            if not existing_baiter:
                self.spawn_baiter()

        # Collisions.
        self.handle_collisions()
        self.handle_human_interactions()

        # Check humans still alive.
        alive_humans = [h for h in self.humans if h.state != "dead"]
        if not alive_humans:
            # Mutant party if everyone is gone.
            self.transform_landers()

        # Clean up projectiles outside vertical bounds.
        for laser in list(self.lasers):
            if laser.world_pos.y < 0 or laser.world_pos.y > SCREEN_HEIGHT:
                laser.kill()
        for shot in list(self.enemy_shots):
            if shot.world_pos.y < 0 or shot.world_pos.y > SCREEN_HEIGHT:
                shot.kill()

        if not self.enemies and not self.pending_spawns:
            self.begin_next_wave()
            return

        if self.message_timer and self.message_timer.update(dt):
            self.message_timer = None
            self.wave_message = None

    def handle_collisions(self):
        def sprite_visible(sprite: WorldSprite, *, margin: int = 0) -> bool:
            rect = sprite.rect
            return (
                rect.right >= -margin
                and rect.left <= SCREEN_WIDTH + margin
                and rect.bottom >= HUD_HEIGHT - margin
                and rect.top <= SCREEN_HEIGHT + margin
            )

        # Player lasers vs enemies.
        for enemy in list(self.enemies):
            if not sprite_visible(enemy, margin=8):
                continue
            hits = pygame.sprite.spritecollide(enemy, self.lasers, False, collided=pygame.sprite.collide_rect)
            if hits:
                destroyed = enemy.take_damage(1)
                if destroyed:
                    self.explosion(enemy.world_pos.x, enemy.world_pos.y)
                for laser in hits:
                    laser.kill()

        for human in list(self.humans):
            if human.state == "dead":
                continue
            hits = pygame.sprite.spritecollide(human, self.lasers, False, collided=pygame.sprite.collide_rect)
            if hits:
                human.die()
                self.explosion(human.world_pos.x, human.world_pos.y)
                for laser in hits:
                    laser.kill()

        if self.player and self.player.invulnerable <= 0:
            if pygame.sprite.spritecollide(self.player, self.enemies, False, collided=pygame.sprite.collide_rect):
                self.explosion(self.player.world_pos.x, self.player.world_pos.y)
                self.player.hit()

        if self.player and self.player.invulnerable <= 0:
            if pygame.sprite.spritecollide(self.player, self.enemy_shots, True, collided=pygame.sprite.collide_rect):
                self.explosion(self.player.world_pos.x, self.player.world_pos.y)
                self.player.hit()

        for human in self.humans:
            if human.state == "dead":
                continue
            # Enemy shots are ignored for colonists to match classic Defender rules.
            pygame.sprite.spritecollide(human, self.enemy_shots, True, collided=pygame.sprite.collide_rect)

    def handle_human_interactions(self):
        if not self.player:
            return

        if not self.player.held_human:
            for human in self.humans:
                if human.state != "falling":
                    continue
                if pygame.sprite.collide_rect(self.player, human):
                    self.player.pickup_human(human)
                    self.player.score += 250
                    self.spawn_score_popup(human.world_pos.x, human.world_pos.y, 250)
                    self.sfx.play("human_pick")
                    break
        else:
            carried = self.player.held_human
            if carried:
                ground_target = terrain_height(carried.world_pos.x) - carried.rect.height / 2
                if self.player.world_pos.y >= ground_target - 12:
                    delivered = self.player.deliver_human()
                    if delivered:
                        self.player.score += 250
                        self.spawn_score_popup(delivered.world_pos.x, delivered.world_pos.y, 250)
                        self.sfx.play("human_drop")

    def colonist_safe_landing(self, human: "Human"):
        if getattr(human, "safe_landing_rewarded", False):
            return
        if self.player:
            self.player.score += 250
        self.spawn_score_popup(human.world_pos.x, human.world_pos.y, 250)
        self.sfx.play("human_drop")
        human.safe_landing_rewarded = True

    def spawn_player_explosion(self, x: float, y: float):
        self.sfx.play("explosion")
        for _ in range(36):
            velocity = pygame.math.Vector2(random.uniform(-240, 240), random.uniform(-240, 240))
            particle = Laser(
                x,
                y,
                velocity,
                ttl=1.6,
                colors=[
                    (255, 240, 140),
                    (255, 180, 90),
                    (255, 80, 80),
                ],
                length=24,
                thickness=4,
                anchor="center",
                color_interval=0.08,
            )
            self.all_sprites.add(particle)

    def spawn_colonist_crater(self, x: float, y: float):
        self.sfx.play("explosion")
        for _ in range(18):
            velocity = pygame.math.Vector2(random.uniform(-120, 120), random.uniform(-80, -10))
            particle = Laser(
                x,
                y,
                velocity,
                ttl=0.9,
                colors=[
                    (255, 180, 120),
                    (255, 160, 80),
                    (120, 80, 40),
                ],
                length=14,
                thickness=3,
                anchor="center",
                color_interval=0.07,
            )
            self.all_sprites.add(particle)

    # Player death triggers a cinematic explosion plus a brief delay before respawn.
    def begin_player_respawn_delay(self):
        if not self.player:
            return
        self.player.lives -= 1
        self.player.render_visible = False
        self.player.invulnerable = max(
            self.player.invulnerable,
            PLAYER_DEATH_RESPAWN_DELAY + PLAYER_DEATH_INVULN,
        )
        if self.player.lives < 0:
            self.respawn_timer = Timer(PLAYER_DEATH_RESPAWN_DELAY)
        else:
            self.respawn_timer = Timer(PLAYER_DEATH_RESPAWN_DELAY)

    # Respawn completes only after shards finish returning and the timer elapses.
    def finish_player_respawn(self):
        if not self.player:
            return
        if self.player.lives < 0:
            self.game_over()
            return
        self.respawn_player()
        self.player.render_visible = True
        self.player.invulnerable = PLAYER_RESPAWN_INVULN + PLAYER_DEATH_INVULN

    def demo_blank_input(self) -> dict[int, bool]:
        return {key: False for key in DEMO_CONTROL_KEYS}

    def start_demo(self):
        if self.demo_active:
            return
        self.demo_prev_no_death = self.no_death
        self.demo_sound_enabled = self.sfx.enabled
        self.demo_active = True
        self.state = "demo"
        self.title_timer = 0.0
        self.demo_stage = "prime_capture"
        self.demo_stage_timer = 0.0
        self.demo_target_lander = None
        self.demo_target_human = None
        self.demo_mutant_observed = False
        self.no_death = False
        self.sfx.enabled = False
        self.setup_world()
        self.start_wave(initial=True)
        if self.player:
            self.player.demo_input = self.demo_blank_input()

    def update_demo(self, dt: float):
        if not self.player:
            return

        if not self.demo_stage:
            self.demo_stage = "prime_capture"
            self.demo_stage_timer = 0.0

        self.demo_stage_timer += dt
        player = self.player
        move_vector = pygame.math.Vector2(0, 0)
        fire = False

        def seek(target_x: float, target_y: float, weight: float = 1.0, max_dx: float = 180.0, max_dy: float = 120.0) -> tuple[float, float]:
            dx = shortest_offset(target_x, player.world_pos.x)
            dy = target_y - player.world_pos.y
            if max_dx > 0:
                move_vector.x += weight * clamp(dx / max_dx, -1.0, 1.0)
            if max_dy > 0:
                move_vector.y += weight * clamp(dy / max_dy, -1.0, 1.0)
            return dx, dy

        def nearest_lander(reference_x: float) -> Optional["Lander"]:
            landers = [enemy for enemy in self.enemies if isinstance(enemy, Lander)]
            if not landers:
                return None
            return min(landers, key=lambda l: abs(shortest_offset(l.world_pos.x, reference_x)))

        if self.demo_stage == "prime_capture":
            if not self.demo_target_human or self.demo_target_human.state in ("dead", "captured"):
                ground_humans = [h for h in self.humans if h.state == "ground"]
                self.demo_target_human = random.choice(ground_humans) if ground_humans else None
                self.demo_stage_timer = 0.0

            if self.demo_target_human:
                seek(self.demo_target_human.world_pos.x, PLAYFIELD_TOP + 150, weight=0.6)
                if not self.demo_target_lander or not self.demo_target_lander.alive():
                    self.demo_target_lander = nearest_lander(self.demo_target_human.world_pos.x)
                if self.demo_target_lander and self.demo_target_human.state == "ground":
                    self.demo_target_human.reserve_for_lander(self.demo_target_lander)
                if self.demo_target_human.state == "captured":
                    self.demo_stage = "rescue"
                    self.demo_stage_timer = 0.0
            else:
                seek(player.world_pos.x, PLAYFIELD_TOP + 150, weight=0.4, max_dx=120, max_dy=80)
                if self.demo_stage_timer > 10.0:
                    self.demo_stage_timer = 0.0
                    self.spawn_wave_enemies()

        elif self.demo_stage == "rescue":
            lander = self.demo_target_lander if self.demo_target_lander and self.demo_target_lander.alive() else None
            if not lander:
                self.demo_stage = "pickup"
                self.demo_stage_timer = 0.0
            else:
                dx, dy = seek(lander.world_pos.x, lander.world_pos.y, weight=1.1, max_dx=160, max_dy=140)
                close = abs(dx) < 140 and abs(dy) < 120
                fire = close
                if not lander.alive() or (self.demo_target_human and self.demo_target_human.state == "falling"):
                    self.demo_stage = "pickup"
                    self.demo_stage_timer = 0.0

        elif self.demo_stage == "pickup":
            human = self.demo_target_human
            if not human or human.state == "dead":
                self.demo_stage = "allow_mutate"
                self.demo_stage_timer = 0.0
            else:
                target_y = human.world_pos.y - 20 if human.state == "falling" else human.world_pos.y - 10
                seek(human.world_pos.x, target_y, weight=0.9, max_dx=120, max_dy=80)
                if human.state == "ground":
                    self.demo_stage = "allow_mutate"
                    self.demo_stage_timer = 0.0
                    self.demo_target_human = human
                elif player.held_human:
                    self.demo_stage = "deliver"
                    self.demo_stage_timer = 0.0

        elif self.demo_stage == "deliver":
            human = self.demo_target_human
            if not human:
                self.demo_stage = "allow_mutate"
                self.demo_stage_timer = 0.0
            else:
                drop_x = human.world_pos.x
                ground_y = terrain_height(drop_x) - 24
                dx, dy = seek(drop_x, ground_y, weight=1.0, max_dx=100, max_dy=80)
                if dy > 0:
                    move_vector.y += 0.6
                if not player.held_human and human.state == "ground":
                    self.demo_stage = "allow_mutate"
                    self.demo_stage_timer = 0.0
                    self.demo_target_lander = None
                    self.demo_target_human = None

        elif self.demo_stage == "allow_mutate":
            fire = False
            seek(player.world_pos.x, PLAYFIELD_TOP + 120, weight=0.3, max_dx=160, max_dy=120)
            if not self.demo_target_human or self.demo_target_human.state == "dead":
                ground_humans = [h for h in self.humans if h.state == "ground"]
                self.demo_target_human = random.choice(ground_humans) if ground_humans else None
                self.demo_stage_timer = 0.0
            if self.demo_target_human and self.demo_target_human.state == "captured":
                self.demo_target_lander = self.demo_target_human.carrier
            if self.demo_target_human and self.demo_target_human.state == "ground":
                if not self.demo_target_lander or not self.demo_target_lander.alive():
                    self.demo_target_lander = nearest_lander(self.demo_target_human.world_pos.x)
                if self.demo_target_lander:
                    self.demo_target_human.reserve_for_lander(self.demo_target_lander)
            if self.demo_target_lander and not self.demo_target_lander.alive():
                self.demo_target_lander = None
            if not any(isinstance(enemy, Lander) for enemy in self.enemies):
                self.spawn_wave_enemies()
            if self.demo_target_lander and self.demo_target_lander.alive():
                offset_dir = 1 if shortest_offset(self.demo_target_lander.world_pos.x, player.world_pos.x) < 0 else -1
                safe_x = wrap_position(self.demo_target_lander.world_pos.x + offset_dir * 260)
                seek(safe_x, PLAYFIELD_TOP + 140, weight=0.6)
            if self.demo_mutant_observed:
                self.demo_stage = "finished"
                self.demo_stage_timer = 0.0
                self.demo_mutant_observed = False

        elif self.demo_stage == "finished":
            fire = False
            seek(player.world_pos.x, PLAYFIELD_TOP + 140, weight=0.4, max_dx=160, max_dy=120)
            if self.demo_stage_timer > 8.0:
                self.demo_stage = "prime_capture"
                self.demo_stage_timer = 0.0
                self.demo_target_human = None
                self.demo_target_lander = None

        else:
            self.demo_stage = "prime_capture"
            self.demo_stage_timer = 0.0

        # Threat avoidance
        avoid = pygame.math.Vector2(0, 0)
        for shot in self.enemy_shots:
            offset = pygame.math.Vector2(shortest_offset(shot.world_pos.x, player.world_pos.x), shot.world_pos.y - player.world_pos.y)
            dist = offset.length()
            if dist and dist < 180:
                avoid -= offset.normalize() * (1.4 - dist / 180)

        for enemy in self.enemies:
            if isinstance(enemy, Lander) and enemy is self.demo_target_lander:
                continue
            offset = pygame.math.Vector2(shortest_offset(enemy.world_pos.x, player.world_pos.x), enemy.world_pos.y - player.world_pos.y)
            dist = offset.length()
            if dist and dist < 200:
                avoid -= offset.normalize() * (1.2 - dist / 200)

        move_vector += avoid
        move_vector.x = clamp(move_vector.x, -1.5, 1.5)
        move_vector.y = clamp(move_vector.y, -1.5, 1.5)

        commands = self.demo_blank_input()
        if move_vector.x > 0.18:
            commands[pygame.K_RIGHT] = True
        elif move_vector.x < -0.18:
            commands[pygame.K_LEFT] = True
        if move_vector.y > 0.18:
            commands[pygame.K_DOWN] = True
        elif move_vector.y < -0.18:
            commands[pygame.K_UP] = True

        if not fire and (pygame.time.get_ticks() // 300) % 3 == 0:
            fire = True
        commands[pygame.K_SPACE] = fire
        self.player.demo_input = commands

    def stop_demo(self):
        if not self.demo_active and self.state != "demo":
            self.state = "title"
            self.title_timer = 0.0
            return
        self.demo_active = False
        self.demo_stage = None
        self.demo_target_lander = None
        self.demo_target_human = None
        self.demo_mutant_observed = False
        self.no_death = self.demo_prev_no_death
        self.sfx.enabled = self.demo_sound_enabled
        self.state = "title"
        self.title_timer = 0.0
        self.setup_world()

    def transform_landers(self):
        for enemy in list(self.enemies):
            if isinstance(enemy, Lander):
                enemy.mutate()
        if not self.ground_destroyed:
            self.ground_destroyed = True
            self.spawn_ground_eruption()
            self.radar_ground_destroyed = True
        self.set_message("Mutant swarm!", 3.0)

    def draw(self):
        """Render the entire frame: player, enemies, HUD, and overlays."""
        self.screen.fill((10, 10, 30))
        self.starfield.draw(self.screen, self.camera_x)

        # Update rects before drawing/collision.
        for sprite in self.all_sprites:
            sprite.update_rect(self.camera_x)
            if isinstance(sprite, Player):
                if not sprite.render_visible:
                    continue
                if sprite.invulnerable > 0:
                    alpha = 150 + int(105 * math.sin(pygame.time.get_ticks() * 0.02))
                    temp = sprite.image.copy()
                    temp.set_alpha(alpha)
                    self.screen.blit(temp, sprite.rect)
                else:
                    self.screen.blit(sprite.image, sprite.rect)
            elif isinstance(sprite, Human) and not sprite.visible:
                continue
            else:
                self.screen.blit(sprite.image, sprite.rect)

        if self.state in ("playing", "game_over"):
            self.draw_ground()
            self.draw_hud()
            if self.state == "game_over":
                self.draw_game_over()
            elif self.message_timer:
                self.draw_hint()
        else:
            self.draw_ground()
            title_text = self.big_font.render("DEFENDER", True, (255, 200, 80))
            prompt = self.font.render("Press Enter to start", True, (200, 255, 200))
            hint = self.font.render("WASD/Arrows move · Space fire · Shift turn · B bomb · H hyperspace", True, (180, 200, 255))
            status = self.font.render(
                "Demo mode" if self.demo_active else "Waiting...",
                True,
                (180, 200, 255),
            )
            self.screen.blit(title_text, title_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 80)))
            self.screen.blit(prompt, prompt.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)))
            self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 40)))
            self.screen.blit(status, status.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 80)))

        pygame.display.flip()

    def draw_ground(self):
        if self.ground_destroyed:
            return
        terrain_points = []
        half_width = SCREEN_WIDTH / 2
        for screen_x in range(0, SCREEN_WIDTH + 4, 4):
            world_x = wrap_position(self.camera_x + (screen_x - half_width))
            y = int(terrain_height(world_x))
            terrain_points.append((screen_x, y))

        if not terrain_points:
            return

        # Base glow pass to suggest the scanner outline.
        pygame.draw.lines(self.screen, (40, 110, 60), False, terrain_points, 6)
        pygame.draw.lines(self.screen, (90, 220, 120), False, terrain_points, 2)

    def draw_hud(self):
        if not self.player:
            return

        panel_rect = pygame.Rect(0, 0, SCREEN_WIDTH, HUD_HEIGHT)
        self.screen.fill((0, 0, 0), panel_rect)
        pygame.draw.rect(self.screen, (0, 200, 80), panel_rect, 3)

        third = panel_rect.width // 3
        left = pygame.Rect(panel_rect.left + 8, panel_rect.top + 8, third - 16, panel_rect.height - 16)
        center = pygame.Rect(panel_rect.left + third + 6, panel_rect.top + 8, third - 12, panel_rect.height - 16)
        right = pygame.Rect(panel_rect.left + 2 * third + 8, panel_rect.top + 8, third - 16, panel_rect.height - 16)

        score_text = self.big_font.render(f"{self.player.score:06d}", True, (255, 255, 140))
        self.screen.blit(score_text, (left.left, left.top))

        line_y = left.top + score_text.get_height() + 4
        for i in range(max(0, self.player.lives)):
            offset = i * (LIFE_ICON_SURFACE.get_width() + 4)
            self.screen.blit(LIFE_ICON_SURFACE, (left.left + offset, line_y))
        line_y += LIFE_ICON_SURFACE.get_height() + 4

        colonists = sum(1 for h in self.humans if h.state != "dead")
        colonist_text = self.font.render(f"Colonists {colonists}/{len(self.humans)}", True, (200, 255, 200))
        self.screen.blit(colonist_text, (left.left, line_y))
        line_y += colonist_text.get_height() + 2

        pygame.draw.rect(self.screen, (0, 200, 80), center, 2)
        self.draw_scanner(center)

        wave_text = self.font.render(f"Wave {self.wave}", True, (220, 255, 220))
        self.screen.blit(wave_text, (right.left, right.top))
        info_y = right.top + wave_text.get_height() + 6
        if self.no_death:
            status = self.font.render("NO-DEATH", True, (255, 120, 255))
            self.screen.blit(status, (right.left, info_y))
            info_y += status.get_height() + 4

        bomb_text = self.font.render(f"Smart Bombs {self.smart_bombs}", True, (255, 240, 160))
        self.screen.blit(bomb_text, (right.left, info_y))
        info_y += bomb_text.get_height() + 4

        if self.hyperspace_cooldown > 0:
            hyper_text = self.font.render(f"Hyperspace {self.hyperspace_cooldown:0.1f}s", True, (180, 220, 255))
            self.screen.blit(hyper_text, (right.left, info_y))

    def draw_hint(self):
        if not self.player:
            return
        hint = self.wave_message or DEFAULT_HINT
        text = self.font.render(hint, True, (255, 255, 180))
        rect = text.get_rect(center=(SCREEN_WIDTH // 2, HUD_HEIGHT + 24))
        self.screen.blit(text, rect)

    def draw_game_over(self):
        text = self.big_font.render("GAME OVER", True, (255, 120, 120))
        rect = text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
        self.screen.blit(text, rect)
        prompt = self.font.render("Press Enter to restart", True, (255, 255, 220))
        prect = prompt.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 60))
        self.screen.blit(prompt, prect)

    def explosion(self, x: float, y: float):
        # Particle spray for visual feedback.
        self.sfx.play("explosion")
        for _ in range(12):
            particle = Laser(
                x,
                y,
                pygame.math.Vector2(random.uniform(-120, 120), random.uniform(-120, 120)),
                ttl=0.28,
                colors=[(255, 200, 120), (255, 160, 80), (255, 240, 200)],
                length=18,
                thickness=3,
                anchor="center",
                color_interval=0.06,
            )
            self.all_sprites.add(particle)

    def spawn_score_popup(self, x: float, y: float, amount: int):
        popup = ScorePopup(
            wrap_position(x),
            y,
            str(amount),
            POPUP_COLORS,
            self.popup_font,
        )
        self.all_sprites.add(popup)

    def spawn_ground_eruption(self):
        samples = max(GROUND_ERUPTION_PARTICLE_COUNT // 6, 1)
        for i in range(samples):
            world_x = random.uniform(0, WORLD_WIDTH)
            y = terrain_height(world_x)
            for _ in range(GROUND_ERUPTION_PARTICLE_COUNT // samples):
                particle = GroundParticle(world_x, y)
                self.all_sprites.add(particle)

    def draw_scanner(self, rect: pygame.Rect):
        if not self.player:
            return

        inner = rect.inflate(-6, -10)
        pygame.draw.rect(self.screen, (0, 20, 0), inner)
        pygame.draw.rect(self.screen, (0, 160, 60), rect, 2)

        player_x = self.player.world_pos.x
        scan_half = inner.width / 2
        center_x = inner.centerx
        play_height = max(1.0, SCREEN_HEIGHT - PLAYFIELD_TOP)
        top_limit = inner.top + 6
        baseline = inner.bottom - 6

        if self.radar_blink_timer > 0 and int(self.radar_blink_timer * 125) % 2 == 0:
            player_color = (255, 90, 90) if self.radar_warning else (255, 255, 255)
        else:
            player_color = (255, 255, 255)
        pygame.draw.line(
            self.screen,
            player_color,
            (center_x, top_limit),
            (center_x, baseline),
            4,
        )

        terrain_points = []
        for i in range(inner.left, inner.right, 3):
            offset = (i - center_x) / scan_half
            world_x = wrap_position(player_x + offset * (WORLD_WIDTH / 2))
            ground = terrain_height(world_x)
            ratio = clamp((ground - PLAYFIELD_TOP) / play_height, 0.0, 1.0)
            y = top_limit + ratio * (baseline - top_limit)
            terrain_points.append((i, int(y)))
        if len(terrain_points) > 1 and not self.radar_ground_destroyed:
            pygame.draw.lines(self.screen, (255, 160, 40), False, terrain_points, 2)

        def draw_marker(entity_pos: pygame.math.Vector2, color: tuple[int, int, int], radius: int = 3):
            dx = shortest_offset(entity_pos.x, player_x) / (WORLD_WIDTH / 2)
            dx = clamp(dx, -1.0, 1.0)
            scanner_x = center_x + dx * scan_half
            ratio = clamp((entity_pos.y - PLAYFIELD_TOP) / play_height, 0.0, 1.0)
            scanner_y = top_limit + ratio * (baseline - top_limit)
            pygame.draw.circle(self.screen, color, (int(scanner_x), int(scanner_y)), radius)

        for enemy in self.enemies:
            if isinstance(enemy, Mutant):
                color = (255, 80, 80)
            elif isinstance(enemy, Bomber):
                color = (120, 200, 255)
            elif isinstance(enemy, Pod):
                color = (255, 120, 255)
            elif isinstance(enemy, Swarmer):
                color = (255, 200, 80)
            elif isinstance(enemy, Baiter):
                color = (255, 255, 255)
            else:
                color = (120, 255, 140)
            draw_marker(enemy.world_pos, color, radius=4 if not isinstance(enemy, Swarmer) else 3)

        for human in self.humans:
            if human.state != "dead":
                draw_marker(human.world_pos, (120, 200, 255), radius=2)

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif self.player and self.state == "playing" and event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
                        self.player.begin_reverse_traverse()
                    elif self.state == "playing" and event.key == SMART_BOMB_KEY:
                        self.activate_smart_bomb()
                    elif self.state == "playing" and event.key == HYPERSPACE_KEY:
                        self.activate_hyperspace()
                    elif event.key == pygame.K_0:
                        self.no_death = not self.no_death
                    if event.key == pygame.K_RETURN:
                        if self.state == "demo":
                            self.stop_demo()
                        elif self.state in ("title", "game_over"):
                            self.stop_demo()
                            self.state = "playing"
                            self.title_timer = 0.0
                            self.demo_active = False
                            self.setup_world()

            self.update(dt)
            self.draw()

        pygame.quit()


def main():
    try:
        pygame.mixer.pre_init(44100, -16, 1, 256)
    except pygame.error:
        pass
    pygame.init()
    pygame.display.set_caption("Defender")
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    game = DefenderGame(screen)
    game.run()


if __name__ == "__main__":
    main()
