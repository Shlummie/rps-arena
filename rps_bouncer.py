"""
Rock Paper Scissors Bouncer
============================

A desktop game where Rock, Paper, and Scissors entities bounce around
and convert each other based on RPS rules.

INSTALLATION:
    pip install pygame

CONTROLS:
    EDIT MODE (default):
        1/2/3/4     - Select brush (Rock/Paper/Scissors/Random)
        Left Click  - Place entity at cursor
        Shift+Click - Place cluster of entities around cursor
        Right Click - Delete nearest entity
        Mouse Wheel - Change spawn count per click (+/- keys also work)
        
    GAME FLOW:
        Space       - Toggle EDIT <-> RUN mode
        R           - Restart simulation (keep entities, randomize velocities)
        C           - Clear all entities
        N           - Generate random setup (equal counts)
        Tab         - Open/close settings menu
        H           - Toggle UI visibility (hide/show all UI)
        A           - Toggle AUTO mode (fullscreen screensaver)
        Escape      - Quit game (or exit auto mode)
        
    SETTINGS MENU (when open):
        Up/Down     - Navigate settings
        Enter       - Edit selected setting (type a value)
        R           - Reset to defaults
        Tab/Escape  - Close menu
        
    WHILE EDITING A VALUE:
        0-9         - Type numbers
        Backspace   - Delete last character
        Enter       - Confirm value
        Escape      - Cancel editing

RULES:
    - Rock beats Scissors (Scissors is deleted)
    - Paper beats Rock (Rock is deleted)  
    - Scissors beats Paper (Paper is deleted)
    - Same type: entities bounce off each other

Author: AI Assistant
"""

import argparse
import json
import math
import os
import queue
import random
import sys
import threading
import time
from collections import deque
from datetime import date
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pygame

# =============================================================================
# CONSTANTS
# =============================================================================

# Window settings
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800
FPS = 60

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "stream_config.json"
SCORES_PATH = BASE_DIR / "stream_scores.json"
SFX_DIR = BASE_DIR / "assets" / "sfx"

# Entity settings
ENTITY_RADIUS = 20
CLUSTER_JITTER = 60  # max offset for cluster placement
DELETE_RADIUS = 50  # max distance to delete entity with right click

# Default settings (can be adjusted in settings menu)
DEFAULT_SPEED_MIN = 100  # pixels per second
DEFAULT_SPEED_MAX = 200
DEFAULT_SEEK_RADIUS = 250  # entities within this range will attract
DEFAULT_SEEK_STRENGTH = 15  # acceleration towards nearby entities (pixels/sec^2)
DEFAULT_PIECE_SIZE = 20  # entity radius in pixels
STREAM_TOP_HUD_HEIGHT = 185
STREAM_BOTTOM_HUD_HEIGHT = 250

# Colors (Dark theme with vibrant accents)
COLOR_BG = (18, 18, 24)
COLOR_BG_EDIT = (22, 22, 32)
COLOR_ROCK = (220, 80, 80)       # Red
COLOR_PAPER = (80, 180, 220)     # Cyan/Blue
COLOR_SCISSORS = (180, 220, 80)  # Lime/Yellow-Green
COLOR_TEXT = (240, 240, 245)
COLOR_TEXT_DIM = (140, 140, 160)
COLOR_HUD_BG = (30, 30, 40, 200)
COLOR_INVALID = (255, 60, 60)
COLOR_VALID = (60, 255, 120)
COLOR_GRID = (35, 35, 50)
COLOR_RANDOM = (200, 150, 255)  # Purple for random brush

DEFAULT_STREAM_CONFIG = {
    "stream_mode": False,
    "preset": "720p",
    "presets": {
        "720p": {"width": 720, "height": 1280},
        "1080p": {"width": 1080, "height": 1920},
    },
    "fullscreen": False,
    "borderless": False,
    "fps": FPS,
    "audio": {
        "enabled": True,
        "device": "",
        "volume": 0.75,
        "fallback_to_default": True,
    },
    "round": {
        "count_per_type": 22,
        "restart_delay": 4.0,
        "piece_size": 18,
        "speed_min": 55,
        "speed_max": 115,
        "seek_radius": 280,
        "seek_strength": 18,
    },
    "events": {
        "server_enabled": True,
        "host": "127.0.0.1",
        "port": 8765,
        "small_spawn_count": 3,
        "medium_spawn_count": 8,
        "large_spawn_count": 12,
        "medium_effect_seconds": 10.0,
        "large_effect_seconds": 12.0,
        "large_event_cooldown": 8.0,
        "max_recent_events": 8,
    },
}

# Entity type enum
class EntityType(Enum):
    ROCK = 0
    PAPER = 1
    SCISSORS = 2

# Type properties
TYPE_COLORS = {
    EntityType.ROCK: COLOR_ROCK,
    EntityType.PAPER: COLOR_PAPER,
    EntityType.SCISSORS: COLOR_SCISSORS,
}

TYPE_LABELS = {
    EntityType.ROCK: "R",
    EntityType.PAPER: "P",
    EntityType.SCISSORS: "S",
}

TYPE_NAMES = {
    EntityType.ROCK: "Rock",
    EntityType.PAPER: "Paper",
    EntityType.SCISSORS: "Scissors",
}

TYPE_KEYS = {
    EntityType.ROCK: "rock",
    EntityType.PAPER: "paper",
    EntityType.SCISSORS: "scissors",
}

KEY_TYPES = {value: key for key, value in TYPE_KEYS.items()}


def deep_merge(defaults: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Merge config dictionaries without mutating either input."""
    merged = dict(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_stream_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_STREAM_CONFIG))

    try:
        with path.open("r", encoding="utf-8") as handle:
            user_config = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not load {path.name}: {exc}. Using defaults.", file=sys.stderr)
        user_config = {}

    return deep_merge(DEFAULT_STREAM_CONFIG, user_config)


def parse_entity_type(value: Any, fallback: Optional[EntityType] = None) -> EntityType:
    if isinstance(value, EntityType):
        return value
    if value is None:
        return fallback if fallback is not None else random.choice(list(EntityType))

    key = str(value).strip().lower()
    aliases = {
        "r": "rock",
        "rock": "rock",
        "p": "paper",
        "paper": "paper",
        "s": "scissors",
        "scissor": "scissors",
        "scissors": "scissors",
        "random": "random",
    }
    key = aliases.get(key, key)
    if key == "random":
        return random.choice(list(EntityType))
    return KEY_TYPES.get(key, fallback if fallback is not None else EntityType.ROCK)


def type_key(entity_type: EntityType) -> str:
    return TYPE_KEYS[entity_type]


def type_name(entity_type: EntityType) -> str:
    return TYPE_NAMES[entity_type]

# Game mode enum
class GameMode(Enum):
    EDIT = 0
    RUN = 1


# =============================================================================
# ENTITY CLASS
# =============================================================================

class Entity:
    """Represents a single Rock, Paper, or Scissors entity."""
    
    def __init__(self, entity_type: EntityType, x: float, y: float, 
                 vx: float = 0, vy: float = 0, radius: float = ENTITY_RADIUS):
        self.type = entity_type
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.radius = radius
        
    @property
    def position(self) -> Tuple[float, float]:
        return (self.x, self.y)
    
    @property
    def velocity(self) -> Tuple[float, float]:
        return (self.vx, self.vy)
    
    def randomize_velocity(self, speed_min: float = DEFAULT_SPEED_MIN, 
                           speed_max: float = DEFAULT_SPEED_MAX):
        """Assign a random velocity within speed bounds."""
        speed = random.uniform(speed_min, speed_max)
        angle = random.uniform(0, 2 * math.pi)
        self.vx = speed * math.cos(angle)
        self.vy = speed * math.sin(angle)
        
    def update(self, dt: float, bounds: Tuple[float, ...]):
        """Update position and bounce off walls."""
        # Move
        self.x += self.vx * dt
        self.y += self.vy * dt
        
        # Bounce off walls
        if len(bounds) == 2:
            left, top = 0, 0
            right, bottom = bounds
        else:
            left, top, right, bottom = bounds

        if self.x - self.radius < left:
            self.x = left + self.radius
            self.vx = abs(self.vx)
        elif self.x + self.radius > right:
            self.x = right - self.radius
            self.vx = -abs(self.vx)
            
        if self.y - self.radius < top:
            self.y = top + self.radius
            self.vy = abs(self.vy)
        elif self.y + self.radius > bottom:
            self.y = bottom - self.radius
            self.vy = -abs(self.vy)
            
    def collides_with(self, other: 'Entity') -> bool:
        """Check if this entity overlaps with another."""
        dx = self.x - other.x
        dy = self.y - other.y
        dist_sq = dx * dx + dy * dy
        min_dist = self.radius + other.radius
        return dist_sq < min_dist * min_dist
    
    def distance_to(self, x: float, y: float) -> float:
        """Calculate distance from entity center to a point."""
        dx = self.x - x
        dy = self.y - y
        return math.sqrt(dx * dx + dy * dy)
    
    def draw(self, surface: pygame.Surface, font: pygame.font.Font, image: pygame.Surface = None):
        """Render the entity using an image if provided, otherwise fallback to circle."""
        if image is not None:
            # Draw the image centered on entity position
            img_rect = image.get_rect(center=(int(self.x), int(self.y)))
            surface.blit(image, img_rect)
        else:
            # Fallback: draw filled circle with border and label
            color = TYPE_COLORS[self.type]
            label = TYPE_LABELS[self.type]
            
            pygame.draw.circle(surface, color, (int(self.x), int(self.y)), int(self.radius))
            pygame.draw.circle(surface, (255, 255, 255), (int(self.x), int(self.y)), int(self.radius), 2)
            
            text = font.render(label, True, (255, 255, 255))
            text_rect = text.get_rect(center=(int(self.x), int(self.y)))
            surface.blit(text, text_rect)


# =============================================================================
# STREAM SUPPORT
# =============================================================================

class SoundManager:
    """Small, fault-tolerant wrapper around pygame.mixer for stream SFX."""

    SOUND_FILES = {
        "convert": "convert_01.wav",
        "spawn_rock": "spawn_rock.wav",
        "spawn_paper": "spawn_paper.wav",
        "spawn_scissors": "spawn_scissors.wav",
        "gift_small": "gift_small.wav",
        "gift_medium": "gift_medium.wav",
        "gift_large": "gift_large.wav",
        "power": "power_up.wav",
        "win_rock": "win_rock.wav",
        "win_paper": "win_paper.wav",
        "win_scissors": "win_scissors.wav",
        "countdown": "countdown.wav",
        "reset": "reset.wav",
    }

    def __init__(self, audio_config: Dict[str, Any]):
        self.enabled = bool(audio_config.get("enabled", True))
        self.master_volume = float(audio_config.get("volume", 0.75))
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        self.last_played: Dict[str, float] = {}
        self.device = str(audio_config.get("device") or "").strip()
        self.fallback_to_default = bool(audio_config.get("fallback_to_default", True))

        if self.enabled:
            self._init_mixer()
            self._load_sounds()

    def _init_mixer(self):
        pygame.mixer.quit()
        kwargs = {
            "frequency": 44100,
            "size": -16,
            "channels": 2,
            "buffer": 512,
        }
        try:
            if self.device:
                pygame.mixer.init(**kwargs, devicename=self.device)
            else:
                pygame.mixer.init(**kwargs)
        except pygame.error as exc:
            if not self.fallback_to_default or not self.device:
                print(f"Audio disabled: {exc}", file=sys.stderr)
                self.enabled = False
                return
            print(f"Audio device '{self.device}' unavailable; using default device.", file=sys.stderr)
            try:
                pygame.mixer.init(**kwargs)
            except pygame.error as fallback_exc:
                print(f"Audio disabled: {fallback_exc}", file=sys.stderr)
                self.enabled = False
                return

        pygame.mixer.set_num_channels(24)

    def _load_sounds(self):
        if not pygame.mixer.get_init():
            self.enabled = False
            return

        for key, filename in self.SOUND_FILES.items():
            path = SFX_DIR / filename
            if not path.exists():
                continue
            try:
                sound = pygame.mixer.Sound(str(path))
                sound.set_volume(self.master_volume)
                self.sounds[key] = sound
            except pygame.error as exc:
                print(f"Could not load SFX {filename}: {exc}", file=sys.stderr)

    def play(self, key: str, volume: float = 1.0, cooldown: float = 0.0):
        if not self.enabled:
            return
        sound = self.sounds.get(key)
        if sound is None:
            return

        now = time.monotonic()
        if cooldown > 0 and now - self.last_played.get(key, 0.0) < cooldown:
            return

        sound.set_volume(max(0.0, min(1.0, self.master_volume * volume)))
        sound.play()
        self.last_played[key] = now

    def play_spawn(self, entity_type: EntityType):
        self.play(f"spawn_{type_key(entity_type)}", volume=0.65, cooldown=0.05)

    def play_win(self, entity_type: EntityType):
        self.play(f"win_{type_key(entity_type)}", volume=1.0)


class Scoreboard:
    """Persistent daily/lifetime stats for unattended stream mode."""

    def __init__(self, path: Path = SCORES_PATH):
        self.path = path
        self.data = self._load()
        self._roll_daily_if_needed()

    def _blank(self) -> Dict[str, Any]:
        keys = [type_key(t) for t in EntityType]
        return {
            "date": date.today().isoformat(),
            "daily_wins": {key: 0 for key in keys},
            "lifetime_wins": {key: 0 for key in keys},
            "total_fake_gifts": 0,
            "supporters": {},
        }

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._blank()
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return self._blank()

        blank = self._blank()
        loaded.setdefault("date", blank["date"])
        loaded.setdefault("daily_wins", blank["daily_wins"])
        loaded.setdefault("lifetime_wins", blank["lifetime_wins"])
        loaded.setdefault("total_fake_gifts", 0)
        loaded.setdefault("supporters", {})
        for key in blank["daily_wins"]:
            loaded["daily_wins"].setdefault(key, 0)
            loaded["lifetime_wins"].setdefault(key, 0)
        return loaded

    def _roll_daily_if_needed(self):
        today = date.today().isoformat()
        if self.data.get("date") == today:
            return
        self.data["date"] = today
        self.data["daily_wins"] = {type_key(t): 0 for t in EntityType}
        self.save()

    def save(self):
        try:
            with self.path.open("w", encoding="utf-8") as handle:
                json.dump(self.data, handle, indent=2)
        except OSError as exc:
            print(f"Could not save scoreboard: {exc}", file=sys.stderr)

    def record_win(self, winner: EntityType):
        key = type_key(winner)
        self._roll_daily_if_needed()
        self.data["daily_wins"][key] = self.data["daily_wins"].get(key, 0) + 1
        self.data["lifetime_wins"][key] = self.data["lifetime_wins"].get(key, 0) + 1
        self.save()

    def record_gift(self, user: str, team: EntityType, tier: str, coins: int):
        user = user.strip() or "viewer"
        tier_points = {"small": 1, "medium": 5, "large": 20}
        points = max(1, int(coins or 0)) if coins else tier_points.get(tier, 1)
        supporters = self.data.setdefault("supporters", {})
        entry = supporters.setdefault(user, {"points": 0, "gifts": 0, "last_team": type_key(team)})
        entry["points"] += points
        entry["gifts"] += 1
        entry["last_team"] = type_key(team)
        self.data["total_fake_gifts"] = self.data.get("total_fake_gifts", 0) + 1
        self.save()

    def top_supporters(self, limit: int = 5) -> List[Tuple[str, Dict[str, Any]]]:
        supporters = self.data.get("supporters", {})
        return sorted(
            supporters.items(),
            key=lambda item: (item[1].get("points", 0), item[1].get("gifts", 0)),
            reverse=True,
        )[:limit]

    def wins_for(self, entity_type: EntityType, daily: bool = True) -> int:
        bucket = "daily_wins" if daily else "lifetime_wins"
        return int(self.data.get(bucket, {}).get(type_key(entity_type), 0))


class EventServer:
    """Background localhost HTTP receiver for gift-shaped test events."""

    def __init__(self, host: str, port: int, event_queue: "queue.Queue[Dict[str, Any]]"):
        self.host = host
        self.port = int(port)
        self.event_queue = event_queue
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        event_queue = self.event_queue

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/health":
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')

            def do_POST(self):
                if self.path != "/event":
                    self.send_error(404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = self.rfile.read(length).decode("utf-8")
                    event = json.loads(payload or "{}")
                    if not isinstance(event, dict):
                        raise ValueError("event must be a JSON object")
                    event_queue.put(event)
                except Exception as exc:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": str(exc)}).encode("utf-8"))
                    return

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')

            def log_message(self, format, *args):
                return

        try:
            self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError as exc:
            print(f"Event server disabled: {exc}", file=sys.stderr)
            return

        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        print(f"Fake event server listening on http://{self.host}:{self.port}/event")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


# =============================================================================
# GAME CLASS
# =============================================================================

class Game:
    """Main game class handling state, input, updates, and rendering."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, force_stream_mode: bool = False):
        self.config = config or load_stream_config()
        self.stream_mode = force_stream_mode or bool(self.config.get("stream_mode", False))
        self.fps = int(self.config.get("fps", FPS))

        pygame.init()
        pygame.display.set_caption(
            "RPS Stream Arena" if self.stream_mode else "Rock Paper Scissors Bouncer"
        )
        
        self.window_width, self.window_height = self.get_configured_window_size()
        display_flags = 0
        if self.stream_mode and bool(self.config.get("borderless", False)):
            display_flags |= pygame.NOFRAME
        if self.stream_mode and bool(self.config.get("fullscreen", False)):
            display_flags |= pygame.FULLSCREEN

        self.screen = pygame.display.set_mode(
            (self.window_width, self.window_height), display_flags
        )
        if display_flags & pygame.FULLSCREEN:
            info = pygame.display.Info()
            self.window_width = info.current_w
            self.window_height = info.current_h

        self.clock = pygame.time.Clock()
        self.running = True
        self.sound = SoundManager(self.config.get("audio", {}))
        
        # Fonts
        self.font_entity = pygame.font.Font(None, 28)
        self.font_hud = pygame.font.Font(None, 32)
        self.font_hud_large = pygame.font.Font(None, 48)
        self.font_controls = pygame.font.Font(None, 24)
        self.font_stream_title = pygame.font.Font(None, 54)
        self.font_stream = pygame.font.Font(None, 30)
        self.font_stream_small = pygame.font.Font(None, 24)
        self.font_banner = pygame.font.Font(None, 64)
        self.font_banner_small = pygame.font.Font(None, 32)
        self.font_float = pygame.font.Font(None, 36)
        
        # Game state
        self.mode = GameMode.EDIT
        self.entities: List[Entity] = []
        self.initial_placements: List[Tuple[EntityType, float, float]] = []
        
        # Edit mode state
        self.selected_brush: Optional[EntityType] = EntityType.ROCK  # None = random
        self.spawn_count = 1
        self.spawn_counts = [1, 5, 10, 25, 50]
        self.spawn_index = 0
        
        # Win state
        self.winner: Optional[EntityType] = None
        
        # Visual feedback
        self.flash_timer = 0
        self.flash_valid = True
        
        # Input state tracking
        self.mouse_held = False
        self.last_placement_pos = None
        
        # Settings menu
        self.settings_open = False
        self.show_ui = True  # Toggle with H key
        
        # Load entity images
        self.original_images = {
            EntityType.ROCK: pygame.image.load(str(BASE_DIR / "rock.png")).convert_alpha(),
            EntityType.PAPER: pygame.image.load(str(BASE_DIR / "paper.png")).convert_alpha(),
            EntityType.SCISSORS: pygame.image.load(str(BASE_DIR / "scissors.png")).convert_alpha(),
        }
        self.entity_images = {}  # Will be scaled versions
        self._last_piece_size = None  # Track for rescaling

        round_config = self.config.get("round", {}) if self.stream_mode else {}
        self.settings = {
            'speed_min': round_config.get('speed_min', DEFAULT_SPEED_MIN),
            'speed_max': round_config.get('speed_max', DEFAULT_SPEED_MAX),
            'seek_radius': round_config.get('seek_radius', DEFAULT_SEEK_RADIUS),
            'seek_strength': round_config.get('seek_strength', DEFAULT_SEEK_STRENGTH),
            'piece_size': round_config.get('piece_size', DEFAULT_PIECE_SIZE),
        }
        self.settings_config = [
            {'key': 'speed_min', 'name': 'Min Speed', 'min': 0, 'max': 1000},
            {'key': 'speed_max', 'name': 'Max Speed', 'min': 0, 'max': 1000},
            {'key': 'seek_radius', 'name': 'Seek Radius', 'min': 0, 'max': 1000},
            {'key': 'seek_strength', 'name': 'Seek Strength', 'min': 0, 'max': 500},
            {'key': 'piece_size', 'name': 'Piece Size', 'min': 5, 'max': 100},
        ]
        self.selected_setting = 0
        self.editing_setting = False  # True when typing in a value
        self.input_text = ""  # Current typed text
        
        # Auto mode (screensaver) state
        self.auto_mode = False
        self.auto_restart_delay = float(round_config.get('restart_delay', 3.0))
        self.auto_restart_timer = 0.0  # countdown timer
        self.winner_recorded = False

        # Stream event/state
        event_config = self.config.get("events", {})
        self.event_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.event_server: Optional[EventServer] = None
        self.scoreboard = Scoreboard()
        self.recent_events = deque(maxlen=int(event_config.get("max_recent_events", 8)))
        self.freeze_until = 0.0
        self.freeze_team: Optional[EntityType] = None
        self.rule_flip_until = 0.0
        self.shield_until = {entity_type: 0.0 for entity_type in EntityType}
        self.boost_until = {entity_type: 0.0 for entity_type in EntityType}
        self.last_large_event_time = 0.0
        self.banner_effects: List[Dict[str, Any]] = []
        self.pulse_effects: List[Dict[str, Any]] = []
        self.float_texts: List[Dict[str, Any]] = []
        self.particles: List[Dict[str, Any]] = []

        if self.stream_mode:
            self.show_ui = True
            pygame.mouse.set_visible(False)
            if bool(event_config.get("server_enabled", True)):
                self.event_server = EventServer(
                    str(event_config.get("host", "127.0.0.1")),
                    int(event_config.get("port", 8765)),
                    self.event_queue,
                )
                self.event_server.start()
            self.auto_start_new_round()

    def get_configured_window_size(self) -> Tuple[int, int]:
        if not self.stream_mode:
            return WINDOW_WIDTH, WINDOW_HEIGHT

        preset_name = str(self.config.get("preset", "720p"))
        presets = self.config.get("presets", {})
        preset = presets.get(preset_name, presets.get("720p", {}))
        width = int(preset.get("width", 720))
        height = int(preset.get("height", 1280))
        return width, height

    def get_playfield_bounds(self) -> Tuple[float, float, float, float]:
        """Return the rectangle where pieces are allowed to move and spawn."""
        if not self.stream_mode:
            return 0.0, 0.0, float(self.window_width), float(self.window_height)

        top = float(STREAM_TOP_HUD_HEIGHT)
        bottom = float(max(top + self.settings['piece_size'] * 2, self.window_height - STREAM_BOTTOM_HUD_HEIGHT))
        return 0.0, top, float(self.window_width), bottom

    def clamp_to_playfield(self, x: float, y: float) -> Tuple[float, float]:
        left, top, right, bottom = self.get_playfield_bounds()
        margin = self.settings['piece_size']
        return (
            max(left + margin, min(right - margin, x)),
            max(top + margin, min(bottom - margin, y)),
        )
        
    def update_scaled_images(self):
        """Scale entity images to match current piece size."""
        piece_size = int(self.settings['piece_size'])
        if piece_size == self._last_piece_size:
            return  # No change needed
            
        self._last_piece_size = piece_size
        diameter = piece_size * 2
        
        for entity_type, original in self.original_images.items():
            scaled = pygame.transform.smoothscale(original, (diameter, diameter))
            self.entity_images[entity_type] = scaled
            
    def run(self):
        """Main game loop."""
        # Initial image scaling
        self.update_scaled_images()

        try:
            while self.running:
                dt = self.clock.tick(self.fps) / 1000.0

                self.handle_events()
                self.update(dt)
                self.render()
        finally:
            if self.event_server:
                self.event_server.stop()
            pygame.quit()
        
    def handle_events(self):
        """Process all pygame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                
            elif event.type == pygame.KEYDOWN:
                self.handle_keydown(event)
                
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.handle_mousedown(event)
                
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self.mouse_held = False
                    self.last_placement_pos = None
                    
            elif event.type == pygame.MOUSEWHEEL:
                self.handle_mousewheel(event)
                
    def handle_keydown(self, event):
        """Handle keyboard input."""
        key = event.key
        
        # Tab or S - toggle settings menu
        if key == pygame.K_TAB or (key == pygame.K_s and not self.settings_open):
            self.settings_open = not self.settings_open
            return
            
        # Settings menu controls
        if self.settings_open:
            self.handle_settings_key(key, event)
            return
        
        # Escape - quit (or exit auto mode first)
        if key == pygame.K_ESCAPE:
            if self.auto_mode:
                self.toggle_auto_mode()  # Exit auto mode
            else:
                self.running = False
            
        # Space - toggle mode
        elif key == pygame.K_SPACE:
            self.toggle_mode()
            
        # R - restart simulation
        elif key == pygame.K_r:
            self.restart_simulation()
            
        # C - clear all
        elif key == pygame.K_c:
            self.clear_entities()
            
        # N - new random setup
        elif key == pygame.K_n:
            self.generate_random_setup()
            
        # 1/2/3/4 - select brush
        elif key == pygame.K_1:
            self.selected_brush = EntityType.ROCK
        elif key == pygame.K_2:
            self.selected_brush = EntityType.PAPER
        elif key == pygame.K_3:
            self.selected_brush = EntityType.SCISSORS
        elif key == pygame.K_4:
            self.selected_brush = None  # Random brush
            
        # +/- change spawn count
        elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.change_spawn_count(1)
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.change_spawn_count(-1)
            
        # H - toggle UI visibility
        elif key == pygame.K_h:
            self.show_ui = not self.show_ui
            
        # A - toggle auto mode (screensaver)
        elif key == pygame.K_a:
            self.toggle_auto_mode()

        # Stream test hotkeys for fake gifts
        elif self.stream_mode and key in (pygame.K_F1, pygame.K_F2, pygame.K_F3):
            team = [EntityType.ROCK, EntityType.PAPER, EntityType.SCISSORS][key - pygame.K_F1]
            self.queue_fake_gift(team, "small", "hotkey", "Hotkey Small")
        elif self.stream_mode and key in (pygame.K_F5, pygame.K_F6, pygame.K_F7):
            team = [EntityType.ROCK, EntityType.PAPER, EntityType.SCISSORS][key - pygame.K_F5]
            self.queue_fake_gift(team, "medium", "hotkey", "Hotkey Medium")
        elif self.stream_mode and key in (pygame.K_F9, pygame.K_F10, pygame.K_F11):
            team = [EntityType.ROCK, EntityType.PAPER, EntityType.SCISSORS][key - pygame.K_F9]
            self.queue_fake_gift(team, "large", "hotkey", "Hotkey Large")
            
    def handle_settings_key(self, key, event):
        """Handle keyboard input in settings menu."""
        
        # If currently editing a value
        if self.editing_setting:
            # Enter - confirm value
            if key == pygame.K_RETURN or key == pygame.K_KP_ENTER:
                self.apply_input_value()
                return
                
            # Escape - cancel editing
            if key == pygame.K_ESCAPE:
                self.editing_setting = False
                self.input_text = ""
                return
                
            # Backspace - delete last character
            if key == pygame.K_BACKSPACE:
                self.input_text = self.input_text[:-1]
                return
                
            # Number keys and decimal point
            if hasattr(event, 'unicode') and event.unicode:
                char = event.unicode
                if char.isdigit() or (char == '.' and '.' not in self.input_text):
                    self.input_text += char
            return
        
        # Not editing - navigation mode
        
        # Escape or Tab - close settings
        if key in (pygame.K_ESCAPE, pygame.K_TAB):
            self.settings_open = False
            return
            
        # Up/Down - navigate settings
        if key == pygame.K_UP:
            self.selected_setting = (self.selected_setting - 1) % len(self.settings_config)
        elif key == pygame.K_DOWN:
            self.selected_setting = (self.selected_setting + 1) % len(self.settings_config)
            
        # Enter - start editing current setting
        elif key == pygame.K_RETURN or key == pygame.K_KP_ENTER:
            config = self.settings_config[self.selected_setting]
            self.editing_setting = True
            self.input_text = str(int(self.settings[config['key']]))
            
        # R - reset to defaults
        elif key == pygame.K_r:
            self.settings = {
                'speed_min': DEFAULT_SPEED_MIN,
                'speed_max': DEFAULT_SPEED_MAX,
                'seek_radius': DEFAULT_SEEK_RADIUS,
                'seek_strength': DEFAULT_SEEK_STRENGTH,
                'piece_size': DEFAULT_PIECE_SIZE,
            }
            
    def apply_input_value(self):
        """Apply the typed input value to the current setting."""
        config = self.settings_config[self.selected_setting]
        setting_key = config['key']
        min_val = config['min']
        max_val = config['max']
        
        try:
            value = float(self.input_text) if '.' in self.input_text else int(self.input_text)
            # Clamp to valid range
            value = max(min_val, min(max_val, value))
            self.settings[setting_key] = value
        except ValueError:
            pass  # Invalid input, keep old value
            
        self.editing_setting = False
        self.input_text = ""
            
    def handle_mousedown(self, event):
        """Handle mouse button press."""
        if self.mode != GameMode.EDIT:
            return
            
        mx, my = event.pos
        
        # Left click - place entity
        if event.button == 1:
            self.mouse_held = True
            mods = pygame.key.get_mods()
            
            if mods & pygame.KMOD_SHIFT:
                # Cluster placement
                self.place_cluster(mx, my)
            else:
                # Single or multi placement
                self.place_entities(mx, my)
                
        # Right click - delete nearest
        elif event.button == 3:
            self.delete_nearest(mx, my)
            
    def handle_mousewheel(self, event):
        """Handle mouse wheel for spawn count."""
        self.change_spawn_count(event.y)
        
    def change_spawn_count(self, direction: int):
        """Change spawn count per click."""
        self.spawn_index = max(0, min(len(self.spawn_counts) - 1, 
                                       self.spawn_index + direction))
        self.spawn_count = self.spawn_counts[self.spawn_index]

    def queue_fake_gift(self, team: EntityType, tier: str, user: str, gift_name: str):
        """Inject the same event shape used by the HTTP bridge."""
        self.event_queue.put({
            "type": "gift",
            "team": type_key(team),
            "tier": tier,
            "user": user,
            "gift_name": gift_name,
            "coins": {"small": 1, "medium": 99, "large": 1000}.get(tier, 1),
        })

    def process_event_queue(self):
        processed = 0
        while processed < 20:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                return
            self.handle_stream_event(event)
            processed += 1

    def handle_stream_event(self, event: Dict[str, Any]):
        event_type = str(event.get("type", "gift")).lower()
        if event_type == "gift":
            self.handle_gift_event(event)
        elif event_type == "spawn":
            team = parse_entity_type(event.get("team"), EntityType.ROCK)
            count = int(event.get("count", 1))
            self.spawn_for_team(team, count)
            self.add_event_feed(f"Spawned {count} {type_name(team)}")
        elif event_type == "reset":
            self.auto_start_new_round()
            self.sound.play("reset", cooldown=0.5)
            self.add_event_feed("Round reset")

    def handle_gift_event(self, event: Dict[str, Any]):
        event_config = self.config.get("events", {})
        team = parse_entity_type(event.get("team"), random.choice(list(EntityType)))
        tier = str(event.get("tier", "small")).lower()
        if tier not in ("small", "medium", "large"):
            tier = "small"
        user = str(event.get("user") or event.get("viewer") or "viewer")
        gift_name = str(event.get("gift_name") or event.get("gift") or tier.title())
        coins = int(event.get("coins") or 0)

        self.scoreboard.record_gift(user, team, tier, coins)

        if tier == "small":
            count = int(event_config.get("small_spawn_count", 3))
            placed = self.spawn_for_team(team, count)
            self.add_gift_visuals(team, tier, user, placed or count)
            self.sound.play("gift_small", cooldown=0.08)
            self.add_event_feed(f"{user}: {gift_name} -> +{count} {type_name(team)}")
        elif tier == "medium":
            count = int(event_config.get("medium_spawn_count", 8))
            placed = self.spawn_for_team(team, count)
            self.apply_medium_effect(team)
            self.add_gift_visuals(team, tier, user, placed or count)
            self.sound.play("gift_medium", cooldown=0.15)
            self.add_event_feed(f"{user}: {gift_name} -> {type_name(team)} boost")
        else:
            self.apply_large_event(team, user, gift_name)

    def apply_medium_effect(self, team: EntityType):
        duration = float(self.config.get("events", {}).get("medium_effect_seconds", 10.0))
        until = time.monotonic() + duration
        self.shield_until[team] = max(self.shield_until[team], until)
        self.boost_until[team] = max(self.boost_until[team], until)
        for entity in self.entities:
            if entity.type == team:
                entity.vx *= 1.25
                entity.vy *= 1.25

    def apply_large_event(self, team: EntityType, user: str, gift_name: str):
        event_config = self.config.get("events", {})
        now = time.monotonic()
        cooldown = float(event_config.get("large_event_cooldown", 8.0))
        if now - self.last_large_event_time < cooldown:
            self.apply_medium_effect(team)
            self.add_gift_visuals(team, "medium", user, int(event_config.get("medium_spawn_count", 8)))
            self.sound.play("gift_medium", cooldown=0.15)
            self.add_event_feed(f"{user}: {gift_name} -> large on cooldown, boosted {type_name(team)}")
            return

        self.last_large_event_time = now
        duration = float(event_config.get("large_effect_seconds", 8.0))
        large_count = int(event_config.get("large_spawn_count", 18))
        until = now + duration
        placed = self.spawn_for_team(team, large_count)
        self.shield_until[team] = max(self.shield_until[team], until)
        self.boost_until[team] = max(self.boost_until[team], until)
        for entity in self.entities:
            if entity.type == team:
                entity.vx *= 1.35
                entity.vy *= 1.35
        self.add_gift_visuals(team, "large", user, placed or large_count)
        message = f"{user}: {gift_name} -> +{large_count} {type_name(team)} mega boost"

        self.sound.play("gift_large", cooldown=0.25)
        self.sound.play("power", cooldown=0.25)
        self.add_event_feed(message)

    def spawn_for_team(self, team: EntityType, count: int) -> int:
        """Spawn entities at random valid positions for stream events."""
        if count <= 0:
            return 0

        piece_size = self.settings['piece_size']
        placed = 0
        attempts = 0
        max_attempts = max(150, count * 60)
        left, top, right, bottom = self.get_playfield_bounds()

        while placed < count and attempts < max_attempts:
            x = random.uniform(left + piece_size, right - piece_size)
            y = random.uniform(top + piece_size, bottom - piece_size)
            if self.is_valid_placement(x, y):
                entity = Entity(team, x, y, radius=piece_size)
                entity.randomize_velocity(self.settings['speed_min'], self.settings['speed_max'])
                self.entities.append(entity)
                placed += 1
            attempts += 1

        if placed:
            self.sound.play_spawn(team)
        return placed

    def add_event_feed(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        self.recent_events.appendleft(f"{timestamp}  {message}")

    def is_entity_frozen(self, entity: Entity) -> bool:
        return (
            self.freeze_team is not None
            and time.monotonic() < self.freeze_until
            and entity.type != self.freeze_team
        )

    def add_banner(self, headline: str, subline: str, color: Tuple[int, int, int], duration: float = 1.8):
        self.banner_effects.append({
            "headline": headline,
            "subline": subline,
            "color": color,
            "age": 0.0,
            "duration": duration,
        })

    def add_team_pulse(self, team: EntityType, strength: float = 1.0, duration: float = 1.0):
        self.pulse_effects.append({
            "team": team,
            "color": TYPE_COLORS[team],
            "strength": strength,
            "age": 0.0,
            "duration": duration,
        })

    def add_float_text(self, text: str, x: float, y: float, color: Tuple[int, int, int], duration: float = 1.3):
        x, y = self.clamp_to_playfield(x, y)
        self.float_texts.append({
            "text": text,
            "x": x,
            "y": y,
            "color": color,
            "age": 0.0,
            "duration": duration,
            "vy": -42.0,
        })

    def add_particles(self, x: float, y: float, color: Tuple[int, int, int], count: int = 18, spread: float = 240.0):
        x, y = self.clamp_to_playfield(x, y)
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(spread * 0.25, spread)
            self.particles.append({
                "x": x,
                "y": y,
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "color": color,
                "age": 0.0,
                "duration": random.uniform(0.45, 0.95),
                "size": random.uniform(3.0, 7.0),
            })

    def add_kill_particles(self, x: float, y: float, color: Tuple[int, int, int]):
        x, y = self.clamp_to_playfield(x, y)
        for _ in range(7):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(42.0, 85.0)
            self.particles.append({
                "x": x,
                "y": y,
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "color": color,
                "age": 0.0,
                "duration": random.uniform(0.28, 0.48),
                "size": random.uniform(1.5, 3.5),
            })

    def add_gift_visuals(self, team: EntityType, tier: str, user: str, count: int):
        color = TYPE_COLORS[team]
        label = {"small": "BOOSTED", "medium": "POWERED UP", "large": "MEGA BOOSTED"}.get(tier, "BOOSTED")
        duration = {"small": 1.15, "medium": 1.55, "large": 2.05}.get(tier, 1.2)
        strength = {"small": 0.75, "medium": 1.1, "large": 1.55}.get(tier, 0.8)
        left, top, right, bottom = self.get_playfield_bounds()
        x = random.uniform(left + 90, right - 90)
        y = random.uniform(top + 90, bottom - 90)
        self.add_banner(f"{user.upper()} {label} {type_name(team).upper()}", f"+{count} {type_name(team)}", color, duration)
        self.add_team_pulse(team, strength=strength, duration=duration)
        self.add_float_text(f"+{count} {type_name(team).upper()}", x, y, color, duration=duration)
        self.add_particles(x, y, color, count={"small": 18, "medium": 34, "large": 58}.get(tier, 18), spread=280.0 * strength)

    def update_visual_effects(self, dt: float):
        for collection in (self.banner_effects, self.pulse_effects, self.float_texts, self.particles):
            for effect in collection:
                effect["age"] += dt

        for text in self.float_texts:
            text["y"] += text["vy"] * dt

        left, top, right, bottom = self.get_playfield_bounds()
        for particle in self.particles:
            particle["x"] += particle["vx"] * dt
            particle["y"] += particle["vy"] * dt
            particle["vy"] += 180 * dt
            if particle["x"] < left or particle["x"] > right:
                particle["vx"] *= -0.65
            if particle["y"] < top or particle["y"] > bottom:
                particle["vy"] *= -0.65

        self.banner_effects = [e for e in self.banner_effects if e["age"] < e["duration"]]
        self.pulse_effects = [e for e in self.pulse_effects if e["age"] < e["duration"]]
        self.float_texts = [e for e in self.float_texts if e["age"] < e["duration"]]
        self.particles = [e for e in self.particles if e["age"] < e["duration"]]
        
    def toggle_mode(self):
        """Switch between EDIT and RUN modes."""
        if self.mode == GameMode.EDIT:
            # Save initial placements and switch to RUN
            self.save_placements()
            self.randomize_all_velocities()
            self.mode = GameMode.RUN
            self.winner = None
            self.winner_recorded = False
        else:
            # Switch back to EDIT, stop movement
            self.mode = GameMode.EDIT
            self.winner = None
            self.winner_recorded = False
            for entity in self.entities:
                entity.vx = 0
                entity.vy = 0
                
    def save_placements(self):
        """Store current entity positions for restart."""
        self.initial_placements = [
            (e.type, e.x, e.y, e.radius) for e in self.entities
        ]
        
    def randomize_all_velocities(self):
        """Randomize velocities of all entities using current settings."""
        for entity in self.entities:
            entity.randomize_velocity(self.settings['speed_min'], 
                                      self.settings['speed_max'])
            
    def restart_simulation(self):
        """Restart with saved placements but new velocities."""
        if not self.initial_placements:
            return
            
        self.entities = [
            Entity(etype, x, y, radius=radius) for etype, x, y, radius in self.initial_placements
        ]
        self.randomize_all_velocities()
        self.mode = GameMode.RUN
        self.winner = None
        self.winner_recorded = False
        
    def clear_entities(self):
        """Remove all entities and go to EDIT mode."""
        self.entities = []
        self.initial_placements = []
        self.mode = GameMode.EDIT
        self.winner = None
        self.winner_recorded = False
        
    def toggle_auto_mode(self):
        """Toggle auto/screensaver mode with fullscreen and auto-restart."""
        self.auto_mode = not self.auto_mode
        
        if self.auto_mode:
            # Enter auto mode - go fullscreen borderless
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN | pygame.NOFRAME)
            info = pygame.display.Info()
            self.window_width = info.current_w
            self.window_height = info.current_h
            
            # Hide UI and mouse cursor
            self.show_ui = False
            pygame.mouse.set_visible(False)
            
            # Start with random setup and run
            self.auto_start_new_round()
        else:
            # Exit auto mode - restore windowed mode
            self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
            self.window_width = WINDOW_WIDTH
            self.window_height = WINDOW_HEIGHT
            
            # Show UI and mouse cursor
            self.show_ui = True
            pygame.mouse.set_visible(True)
            
            # Go back to edit mode
            self.mode = GameMode.EDIT
            self.winner = None
            self.winner_recorded = False
            self.auto_restart_timer = 0.0
            for entity in self.entities:
                entity.vx = 0
                entity.vy = 0
                
    def auto_start_new_round(self):
        """Start a new round in auto mode with random entities."""
        self.entities = []
        piece_size = self.settings['piece_size']
        round_config = self.config.get("round", {}) if self.stream_mode else {}
        count_per_type = int(round_config.get("count_per_type", 15))
        left, top, right, bottom = self.get_playfield_bounds()
        self.freeze_until = 0.0
        self.freeze_team = None
        self.rule_flip_until = 0.0
        self.shield_until = {entity_type: 0.0 for entity_type in EntityType}
        self.boost_until = {entity_type: 0.0 for entity_type in EntityType}
        
        for entity_type in EntityType:
            placed = 0
            attempts = 0
            max_attempts = 1000
            
            while placed < count_per_type and attempts < max_attempts:
                x = random.uniform(left + piece_size, right - piece_size)
                y = random.uniform(top + piece_size, bottom - piece_size)
                
                if self.is_valid_placement(x, y):
                    self.entities.append(Entity(entity_type, x, y, radius=piece_size))
                    placed += 1
                attempts += 1
                
        self.save_placements()
        self.randomize_all_velocities()
        self.mode = GameMode.RUN
        self.winner = None
        self.winner_recorded = False
        self.auto_restart_timer = 0.0
        if self.stream_mode:
            self.sound.play("reset", cooldown=0.5)
        
    def generate_random_setup(self, count_per_type: int = 15):
        """Generate random entities with equal counts."""
        self.entities = []
        piece_size = self.settings['piece_size']
        left, top, right, bottom = self.get_playfield_bounds()
        
        for entity_type in EntityType:
            placed = 0
            attempts = 0
            max_attempts = 1000
            
            while placed < count_per_type and attempts < max_attempts:
                x = random.uniform(left + piece_size, right - piece_size)
                y = random.uniform(top + piece_size, bottom - piece_size)
                
                if self.is_valid_placement(x, y):
                    self.entities.append(Entity(entity_type, x, y, radius=piece_size))
                    placed += 1
                attempts += 1
                
        self.save_placements()
        self.mode = GameMode.EDIT
        self.winner = None
        self.winner_recorded = False
        
    def get_brush_type(self) -> EntityType:
        """Get the entity type to place. Returns random if brush is None."""
        if self.selected_brush is None:
            return random.choice(list(EntityType))
        return self.selected_brush
        
    def is_valid_placement(self, x: float, y: float, 
                           exclude: Optional[Entity] = None) -> bool:
        """Check if a position is valid for placing an entity."""
        piece_size = self.settings['piece_size']
        left, top, right, bottom = self.get_playfield_bounds()
        
        # Check bounds
        if (x - piece_size < left or x + piece_size > right or
            y - piece_size < top or y + piece_size > bottom):
            return False
            
        # Check overlap with existing entities
        for entity in self.entities:
            if entity is exclude:
                continue
            min_dist = piece_size + entity.radius
            dx = x - entity.x
            dy = y - entity.y
            if dx * dx + dy * dy < min_dist * min_dist:
                return False
                
        return True
        
    def place_entities(self, mx: float, my: float):
        """Place one or more entities at/around mouse position."""
        placed = 0
        piece_size = self.settings['piece_size']
        
        if self.spawn_count == 1:
            # Single placement at exact position
            if self.is_valid_placement(mx, my):
                self.entities.append(Entity(self.get_brush_type(), mx, my, radius=piece_size))
                placed = 1
        else:
            # Multi placement in a pattern around cursor
            attempts = 0
            max_attempts = self.spawn_count * 20
            
            while placed < self.spawn_count and attempts < max_attempts:
                if placed == 0:
                    x, y = mx, my
                else:
                    # Spiral outward pattern
                    angle = placed * 2.4  # Golden angle
                    dist = piece_size * 2.2 * math.sqrt(placed)
                    x = mx + dist * math.cos(angle)
                    y = my + dist * math.sin(angle)
                    
                if self.is_valid_placement(x, y):
                    self.entities.append(Entity(self.get_brush_type(), x, y, radius=piece_size))
                    placed += 1
                attempts += 1
                
        # Visual feedback
        self.flash_valid = placed > 0
        self.flash_timer = 0.15
        if placed > 0 and self.selected_brush is not None:
            self.sound.play_spawn(self.selected_brush)
        
    def place_cluster(self, mx: float, my: float):
        """Place a cluster of entities with random jitter."""
        placed = 0
        attempts = 0
        max_attempts = self.spawn_count * 30
        piece_size = self.settings['piece_size']
        
        while placed < self.spawn_count and attempts < max_attempts:
            # Random position with jitter
            jitter_x = random.uniform(-CLUSTER_JITTER, CLUSTER_JITTER)
            jitter_y = random.uniform(-CLUSTER_JITTER, CLUSTER_JITTER)
            x = mx + jitter_x
            y = my + jitter_y
            
            if self.is_valid_placement(x, y):
                self.entities.append(Entity(self.get_brush_type(), x, y, radius=piece_size))
                placed += 1
            attempts += 1
            
        # Visual feedback
        self.flash_valid = placed > 0
        self.flash_timer = 0.15
        if placed > 0 and self.selected_brush is not None:
            self.sound.play_spawn(self.selected_brush)
        
    def delete_nearest(self, mx: float, my: float):
        """Delete the nearest entity within DELETE_RADIUS."""
        nearest = None
        nearest_dist = float('inf')
        
        for entity in self.entities:
            dist = entity.distance_to(mx, my)
            if dist < nearest_dist and dist < DELETE_RADIUS:
                nearest = entity
                nearest_dist = dist
                
        if nearest:
            self.entities.remove(nearest)
            
    def update(self, dt: float):
        """Update game state."""
        if self.stream_mode:
            self.process_event_queue()
            self.update_visual_effects(dt)

        # Update flash timer
        if self.flash_timer > 0:
            self.flash_timer -= dt
            
        # Handle auto-restart in unattended modes when there's a winner
        if (self.auto_mode or self.stream_mode) and self.winner is not None:
            self.auto_restart_timer += dt
            if self.auto_restart_timer >= self.auto_restart_delay:
                self.auto_start_new_round()
            return  # Don't update physics while showing winner
            
        # Only update physics in RUN mode
        if self.mode != GameMode.RUN:
            return
            
        # Apply seek behavior (entities gently attract each other)
        self.apply_seek_forces(dt)
            
        # Update entity positions
        bounds = self.get_playfield_bounds()
        for entity in self.entities:
            if self.is_entity_frozen(entity):
                continue
            entity.update(dt, bounds)
            
        # Handle collisions
        self.handle_collisions()
        
        # Check for winner
        self.check_winner()
        
    def apply_seek_forces(self, dt: float):
        """Apply gentle attraction between nearby entities of DIFFERENT types to speed up endgame."""
        seek_radius = self.settings['seek_radius']
        seek_strength = self.settings['seek_strength']
        
        # Skip if seek is disabled
        if seek_radius <= 0 or seek_strength <= 0:
            return
            
        n = len(self.entities)
        
        for i in range(n):
            e1 = self.entities[i]
            seek_x, seek_y = 0.0, 0.0
            neighbor_count = 0
            
            for j in range(n):
                if i == j:
                    continue
                    
                e2 = self.entities[j]
                
                # Only seek entities of different types
                if e1.type == e2.type:
                    continue
                    
                dx = e2.x - e1.x
                dy = e2.y - e1.y
                dist = math.sqrt(dx * dx + dy * dy)
                
                if dist < seek_radius and dist > 0.001:
                    # Weight closer entities more strongly
                    weight = 1.0 - (dist / seek_radius)
                    seek_x += (dx / dist) * weight
                    seek_y += (dy / dist) * weight
                    neighbor_count += 1
                    
            if neighbor_count > 0:
                # Normalize and apply acceleration
                mag = math.sqrt(seek_x * seek_x + seek_y * seek_y)
                if mag > 0.001:
                    seek_x /= mag
                    seek_y /= mag
                    e1.vx += seek_x * seek_strength * dt
                    e1.vy += seek_y * seek_strength * dt
                    
    def check_winner(self):
        """Check if only one type remains and set winner."""
        if len(self.entities) == 0:
            self.winner = None
            self.winner_recorded = False
            return
            
        # Count types present
        types_present = set(e.type for e in self.entities)
        
        if len(types_present) == 1:
            new_winner = list(types_present)[0]
            if self.winner != new_winner:
                self.winner_recorded = False
            self.winner = new_winner
            if not self.winner_recorded:
                self.scoreboard.record_win(self.winner)
                self.sound.play_win(self.winner)
                self.add_event_feed(f"{type_name(self.winner)} wins the round")
                self.winner_recorded = True
        else:
            self.winner = None
            self.winner_recorded = False
        
    def handle_collisions(self):
        """Check and resolve all entity collisions."""
        entities_to_remove = set()
        
        # First pass: determine RPS outcomes (who gets deleted)
        n = len(self.entities)
        for i in range(n):
            for j in range(i + 1, n):
                e1 = self.entities[i]
                e2 = self.entities[j]
                
                if e1.collides_with(e2):
                    # Resolve RPS outcome - returns the loser to be deleted
                    loser = self.resolve_rps(e1, e2)
                    if loser is not None:
                        entities_to_remove.add(loser)
        
        # Remove defeated entities
        removed_count = 0
        burst_points = []
        for entity in entities_to_remove:
            if entity in self.entities:
                burst_points.append((entity.x, entity.y, TYPE_COLORS[entity.type]))
                self.entities.remove(entity)
                removed_count += 1
        if removed_count:
            self.sound.play("convert", volume=0.55, cooldown=0.12)
            if self.stream_mode:
                for x, y, color in burst_points[:10]:
                    self.add_kill_particles(x, y, color)
        
        # Second pass: separate same-type entities that are still overlapping
        # Run multiple iterations to fully separate clusters
        for _ in range(3):
            n = len(self.entities)
            for i in range(n):
                for j in range(i + 1, n):
                    e1 = self.entities[i]
                    e2 = self.entities[j]
                    
                    if e1.collides_with(e2):
                        self.separate_entities(e1, e2)
                    
    def resolve_rps(self, e1: Entity, e2: Entity) -> Optional[Entity]:
        """Apply Rock-Paper-Scissors rules. Returns the losing entity to delete, or None if same type."""
        t1, t2 = e1.type, e2.type

        if t1 == t2:
            return None

        loser = None
        if t1 == EntityType.ROCK and t2 == EntityType.SCISSORS:
            loser = e2
        elif t1 == EntityType.SCISSORS and t2 == EntityType.ROCK:
            loser = e1
        elif t1 == EntityType.PAPER and t2 == EntityType.ROCK:
            loser = e2
        elif t1 == EntityType.ROCK and t2 == EntityType.PAPER:
            loser = e1
        elif t1 == EntityType.SCISSORS and t2 == EntityType.PAPER:
            loser = e2
        elif t1 == EntityType.PAPER and t2 == EntityType.SCISSORS:
            loser = e1

        if loser is None:
            return None

        if time.monotonic() < self.rule_flip_until:
            loser = e1 if loser is e2 else e2

        if time.monotonic() < self.shield_until.get(loser.type, 0.0):
            return None

        return loser
            
    def separate_entities(self, e1: Entity, e2: Entity):
        """Push apart overlapping entities with elastic collision response."""
        dx = e2.x - e1.x
        dy = e2.y - e1.y
        dist = math.sqrt(dx * dx + dy * dy)
        
        if dist < 0.001:
            # Entities at same position, push in random direction
            angle = random.uniform(0, 2 * math.pi)
            dx = math.cos(angle)
            dy = math.sin(angle)
            dist = 0.001
            
        # Calculate overlap
        min_dist = e1.radius + e2.radius
        overlap = min_dist - dist
        
        if overlap > 0:
            # Normalize direction
            nx = dx / dist
            ny = dy / dist
            
            # Push each entity by half the overlap plus extra buffer
            push = overlap / 2 + 2.0
            e1.x -= nx * push
            e1.y -= ny * push
            e2.x += nx * push
            e2.y += ny * push
            
            # Bounce velocities off each other (elastic collision)
            # Calculate relative velocity
            dvx = e1.vx - e2.vx
            dvy = e1.vy - e2.vy
            
            # Calculate relative velocity in collision normal direction
            dvn = dvx * nx + dvy * ny
            
            # Only resolve if velocities are approaching
            if dvn > 0:
                # Update velocities (equal mass elastic collision)
                e1.vx -= dvn * nx
                e1.vy -= dvn * ny
                e2.vx += dvn * nx
                e2.vy += dvn * ny
            
    def render(self):
        """Draw everything to screen."""
        # Background
        bg_color = COLOR_BG_EDIT if self.mode == GameMode.EDIT else COLOR_BG
        self.screen.fill(bg_color)
        
        # Draw subtle grid in EDIT mode
        if self.mode == GameMode.EDIT:
            self.draw_grid()
            
        # Update scaled images if piece size changed
        self.update_scaled_images()
        
        # Draw entities with their images
        for entity in self.entities:
            image = self.entity_images.get(entity.type)
            entity.draw(self.screen, self.font_entity, image)

        if self.stream_mode:
            self.draw_visual_effects()
            
        # Draw placement preview in EDIT mode
        if self.mode == GameMode.EDIT and self.show_ui:
            self.draw_placement_preview()
            
        # Draw flash feedback
        if self.flash_timer > 0:
            self.draw_flash()
        
        # Draw UI elements if visible
        if self.show_ui:
            if self.stream_mode:
                self.draw_stream_hud()
            else:
                self.draw_hud()
            
            # Draw settings menu if open
            if self.settings_open:
                self.draw_settings_menu()
        else:
            # In auto mode, still show winner splash
            if self.auto_mode and self.winner is not None:
                self.draw_winner_splash()
            elif not self.auto_mode:
                # Show minimal hint when UI is hidden (not in auto mode)
                hint_font = pygame.font.Font(None, 24)
                hint = hint_font.render("Press H to show UI", True, (100, 100, 120))
                self.screen.blit(hint, (10, self.window_height - 30))
        
        pygame.display.flip()

    def draw_translucent_rect(self, rect: pygame.Rect, color: Tuple[int, int, int, int]):
        panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        panel.fill(color)
        self.screen.blit(panel, rect.topleft)

    def draw_visual_effects(self):
        """Draw transient stream effects over the arena and under the HUD."""
        left, top, right, bottom = self.get_playfield_bounds()
        playfield_w = int(right - left)
        playfield_h = int(bottom - top)

        for pulse in self.pulse_effects:
            progress = pulse["age"] / max(0.001, pulse["duration"])
            alpha = int((1.0 - progress) * 90 * pulse["strength"])
            if alpha <= 0:
                continue
            surf = pygame.Surface((playfield_w, playfield_h), pygame.SRCALPHA)
            color = pulse["color"]
            surf.fill((*color, max(0, min(120, alpha // 2))))
            stripe_gap = 46
            offset = int(progress * stripe_gap * 2)
            for x in range(-playfield_h, playfield_w + playfield_h, stripe_gap):
                pygame.draw.line(
                    surf,
                    (*color, max(0, min(150, alpha))),
                    (x + offset, 0),
                    (x + offset + playfield_h, playfield_h),
                    5,
                )
            self.screen.blit(surf, (left, top))

        for particle in self.particles:
            progress = particle["age"] / max(0.001, particle["duration"])
            alpha = int((1.0 - progress) * 230)
            if alpha <= 0:
                continue
            radius = max(1, int(particle["size"] * (1.0 + progress * 0.7)))
            pygame.draw.circle(
                self.screen,
                (*particle["color"], max(0, min(255, alpha))),
                (int(particle["x"]), int(particle["y"])),
                radius,
            )

        for text in self.float_texts:
            progress = text["age"] / max(0.001, text["duration"])
            alpha = int((1.0 - progress) * 255)
            if alpha <= 0:
                continue
            surf = self.font_float.render(text["text"], True, text["color"])
            surf.set_alpha(alpha)
            shadow = self.font_float.render(text["text"], True, (0, 0, 0))
            shadow.set_alpha(max(0, alpha - 45))
            rect = surf.get_rect(center=(int(text["x"]), int(text["y"])))
            self.screen.blit(shadow, rect.move(2, 2))
            self.screen.blit(surf, rect)

        for banner in self.banner_effects[-2:]:
            progress = banner["age"] / max(0.001, banner["duration"])
            alpha = int(min(1.0, (1.0 - progress) * 1.4) * 240)
            if alpha <= 0:
                continue
            scale = 1.0 + math.sin(min(1.0, progress) * math.pi) * 0.035
            color = banner["color"]
            banner_w = min(self.window_width - 48, int(640 * scale))
            banner_h = 128
            banner_x = (self.window_width - banner_w) // 2
            banner_y = int(top + 42)
            panel = pygame.Surface((banner_w, banner_h), pygame.SRCALPHA)
            panel.fill((10, 10, 16, max(0, min(220, alpha))))
            pygame.draw.rect(panel, (*color, max(0, min(255, alpha))), panel.get_rect(), 4, border_radius=12)
            pygame.draw.rect(panel, (*color, max(0, min(90, alpha // 2))), panel.get_rect().inflate(-14, -14), 2, border_radius=8)
            self.screen.blit(panel, (banner_x, banner_y))

            headline = self.font_banner.render(banner["headline"], True, color)
            headline.set_alpha(alpha)
            subline = self.font_banner_small.render(banner["subline"], True, COLOR_TEXT)
            subline.set_alpha(alpha)
            headline_rect = headline.get_rect(center=(self.window_width // 2, banner_y + 45))
            subline_rect = subline.get_rect(center=(self.window_width // 2, banner_y + 88))
            self.screen.blit(headline, headline_rect)
            self.screen.blit(subline, subline_rect)

    def draw_stream_hud(self):
        """Draw a vertical overlay optimized for OBS capture."""
        counts = {t: 0 for t in EntityType}
        for entity in self.entities:
            counts[entity.type] += 1

        top_rect = pygame.Rect(0, 0, self.window_width, STREAM_TOP_HUD_HEIGHT)
        bottom_rect = pygame.Rect(
            0,
            self.window_height - STREAM_BOTTOM_HUD_HEIGHT,
            self.window_width,
            STREAM_BOTTOM_HUD_HEIGHT,
        )
        self.draw_translucent_rect(top_rect, (12, 12, 18, 215))
        self.draw_translucent_rect(bottom_rect, (12, 12, 18, 220))

        title = self.font_stream_title.render("RPS LIVE ARENA", True, COLOR_TEXT)
        self.screen.blit(title, (22, 16))

        block_w = max(140, (self.window_width - 48) // 3)
        block_y = 78
        for idx, entity_type in enumerate(EntityType):
            x = 20 + idx * block_w
            color = TYPE_COLORS[entity_type]
            score = self.scoreboard.wins_for(entity_type, daily=True)
            label = f"{type_name(entity_type)} {counts[entity_type]}"
            label_surf = self.font_stream.render(label, True, color)
            score_surf = self.font_stream_small.render(f"Daily wins: {score}", True, COLOR_TEXT_DIM)
            self.screen.blit(label_surf, (x, block_y))
            self.screen.blit(score_surf, (x, block_y + 32))

        event_title = self.font_stream.render("Recent events", True, COLOR_TEXT)
        self.screen.blit(event_title, (22, bottom_rect.top + 18))
        y = bottom_rect.top + 54
        if self.recent_events:
            for line in list(self.recent_events)[:5]:
                text = line if len(line) <= 48 else line[:45] + "..."
                surf = self.font_stream_small.render(text, True, COLOR_TEXT_DIM)
                self.screen.blit(surf, (24, y))
                y += 28
        else:
            hint = "F1/F2/F3 small gifts, F5/F6/F7 medium, F9/F10/F11 large"
            surf = self.font_stream_small.render(hint, True, COLOR_TEXT_DIM)
            self.screen.blit(surf, (24, y))

        right_x = max(24, self.window_width // 2 + 22)
        top_title = self.font_stream.render("Top supporters", True, COLOR_TEXT)
        self.screen.blit(top_title, (right_x, bottom_rect.top + 18))
        y = bottom_rect.top + 54
        for name, entry in self.scoreboard.top_supporters(5):
            text = f"{name[:14]}  {entry.get('points', 0)} pts"
            surf = self.font_stream_small.render(text, True, COLOR_TEXT_DIM)
            self.screen.blit(surf, (right_x, y))
            y += 28

        event_config = self.config.get("events", {})
        server_text = f"Fake events: http://{event_config.get('host', '127.0.0.1')}:{event_config.get('port', 8765)}/event"
        server_surf = self.font_stream_small.render(server_text, True, (100, 180, 255))
        self.screen.blit(server_surf, (24, self.window_height - 34))

        if self.winner is not None and self.mode == GameMode.RUN:
            self.draw_winner_splash()
        
    def draw_grid(self):
        """Draw a subtle background grid."""
        spacing = 50
        for x in range(0, self.window_width, spacing):
            pygame.draw.line(self.screen, COLOR_GRID, (x, 0), (x, self.window_height))
        for y in range(0, self.window_height, spacing):
            pygame.draw.line(self.screen, COLOR_GRID, (0, y), (self.window_width, y))
            
    def draw_placement_preview(self):
        """Draw a ghost of the entity at cursor position."""
        mx, my = pygame.mouse.get_pos()
        valid = self.is_valid_placement(mx, my)
        piece_size = int(self.settings['piece_size'])
        
        # Get color for preview (use purple for random brush)
        if self.selected_brush is None:
            color = COLOR_RANDOM
        else:
            color = TYPE_COLORS[self.selected_brush]
        
        # Create transparent surface
        ghost_surf = pygame.Surface((piece_size * 2, piece_size * 2), pygame.SRCALPHA)
        pygame.draw.circle(ghost_surf, (*color, 80), 
                          (piece_size, piece_size), piece_size)
        
        # Draw outline indicating validity
        outline_color = COLOR_VALID if valid else COLOR_INVALID
        pygame.draw.circle(ghost_surf, (*outline_color, 150), 
                          (piece_size, piece_size), piece_size, 2)
        
        # Draw "?" for random brush
        if self.selected_brush is None:
            text = self.font_entity.render("?", True, (255, 255, 255, 150))
            text_rect = text.get_rect(center=(piece_size, piece_size))
            ghost_surf.blit(text, text_rect)
        
        self.screen.blit(ghost_surf, (mx - piece_size, my - piece_size))
        
    def draw_flash(self):
        """Draw flash feedback for placement."""
        alpha = int(100 * (self.flash_timer / 0.15))
        color = COLOR_VALID if self.flash_valid else COLOR_INVALID
        
        flash_surf = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        flash_surf.fill((*color, alpha // 4))
        self.screen.blit(flash_surf, (0, 0))
        
    def draw_hud(self):
        """Draw heads-up display with game info."""
        padding = 15
        y_offset = padding
        
        # Count entities by type
        counts = {t: 0 for t in EntityType}
        for entity in self.entities:
            counts[entity.type] += 1
        total = len(self.entities)
        
        # Mode indicator (top center)
        mode_text = "EDIT MODE" if self.mode == GameMode.EDIT else "RUNNING"
        mode_color = (100, 200, 255) if self.mode == GameMode.EDIT else (100, 255, 150)
        mode_surf = self.font_hud_large.render(mode_text, True, mode_color)
        mode_rect = mode_surf.get_rect(midtop=(self.window_width // 2, padding))
        
        # Mode background
        bg_rect = mode_rect.inflate(30, 10)
        pygame.draw.rect(self.screen, (30, 30, 45), bg_rect, border_radius=8)
        pygame.draw.rect(self.screen, mode_color, bg_rect, 2, border_radius=8)
        self.screen.blit(mode_surf, mode_rect)
        
        # Entity counts (top left)
        count_lines = [
            f"Total: {total}",
            f"Rock: {counts[EntityType.ROCK]}",
            f"Paper: {counts[EntityType.PAPER]}",
            f"Scissors: {counts[EntityType.SCISSORS]}",
        ]
        
        count_colors = [
            COLOR_TEXT,
            COLOR_ROCK,
            COLOR_PAPER,
            COLOR_SCISSORS,
        ]
        
        for i, (line, color) in enumerate(zip(count_lines, count_colors)):
            text = self.font_hud.render(line, True, color)
            self.screen.blit(text, (padding, y_offset + i * 28))
            
        # Brush and spawn info (top right) - only in EDIT mode
        if self.mode == GameMode.EDIT:
            if self.selected_brush is None:
                brush_name = "Random"
                brush_color = COLOR_RANDOM
            else:
                brush_name = TYPE_NAMES[self.selected_brush]
                brush_color = TYPE_COLORS[self.selected_brush]
            
            info_lines = [
                (f"Brush: {brush_name}", brush_color),
                (f"Count: {self.spawn_count}", COLOR_TEXT),
            ]
            
            for i, (line, color) in enumerate(info_lines):
                text = self.font_hud.render(line, True, color)
                text_rect = text.get_rect(topright=(self.window_width - padding, y_offset + i * 28))
                self.screen.blit(text, text_rect)
        
        # Draw winner splash if game is won
        if self.winner is not None and self.mode == GameMode.RUN:
            self.draw_winner_splash()
                
        # Controls (bottom)
        self.draw_controls()
        
    def draw_winner_splash(self):
        """Draw a large victory splash when one team wins."""
        winner_name = TYPE_NAMES[self.winner].upper()
        winner_color = TYPE_COLORS[self.winner]
        
        # Create large font for splash
        splash_font = pygame.font.Font(None, 120)
        sub_font = pygame.font.Font(None, 48)
        
        # Main text
        main_text = splash_font.render(f"{winner_name} WINS!", True, winner_color)
        main_rect = main_text.get_rect(center=(self.window_width // 2, self.window_height // 2 - 30))
        
        # Sub text - different message in auto mode
        if self.auto_mode or self.stream_mode:
            remaining = max(0, self.auto_restart_delay - self.auto_restart_timer)
            sub_msg = f"Restarting in {remaining:.1f}s... (Esc to exit)"
        else:
            sub_msg = "Press C to clear or Space to pause"
        sub_text = sub_font.render(sub_msg, True, COLOR_TEXT_DIM)
        sub_rect = sub_text.get_rect(center=(self.window_width // 2, self.window_height // 2 + 50))
        
        # Draw semi-transparent overlay
        overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))
        
        # Draw background box for main text
        box_rect = main_rect.inflate(60, 40)
        pygame.draw.rect(self.screen, (20, 20, 30), box_rect, border_radius=15)
        pygame.draw.rect(self.screen, winner_color, box_rect, 4, border_radius=15)
        
        # Draw texts
        self.screen.blit(main_text, main_rect)
        self.screen.blit(sub_text, sub_rect)
        
    def draw_settings_menu(self):
        """Draw the settings menu overlay with text input fields."""
        # Semi-transparent overlay
        overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        
        # Menu dimensions
        menu_width = 450
        menu_height = 430
        menu_x = (self.window_width - menu_width) // 2
        menu_y = (self.window_height - menu_height) // 2
        
        # Draw menu background
        menu_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(self.screen, (25, 25, 35), menu_rect, border_radius=15)
        pygame.draw.rect(self.screen, (100, 150, 255), menu_rect, 3, border_radius=15)
        
        # Title
        title_font = pygame.font.Font(None, 56)
        title = title_font.render("SETTINGS", True, (100, 150, 255))
        title_rect = title.get_rect(midtop=(self.window_width // 2, menu_y + 20))
        self.screen.blit(title, title_rect)
        
        # Settings items
        item_font = pygame.font.Font(None, 36)
        value_font = pygame.font.Font(None, 38)
        
        start_y = menu_y + 90
        item_height = 55
        
        for i, config in enumerate(self.settings_config):
            y = start_y + i * item_height
            is_selected = (i == self.selected_setting)
            is_editing = is_selected and self.editing_setting
            
            # Row background if selected
            if is_selected:
                row_rect = pygame.Rect(menu_x + 20, y - 8, menu_width - 40, item_height - 5)
                pygame.draw.rect(self.screen, (40, 45, 60), row_rect, border_radius=8)
                border_color = (255, 200, 100) if is_editing else (100, 150, 255)
                pygame.draw.rect(self.screen, border_color, row_rect, 2, border_radius=8)
            
            # Setting name
            name_color = (255, 255, 255) if is_selected else (180, 180, 190)
            name_text = item_font.render(config['name'], True, name_color)
            self.screen.blit(name_text, (menu_x + 35, y))
            
            # Input field box
            input_x = menu_x + 250
            input_y = y - 2
            input_width = 120
            input_height = 36
            
            # Input field background
            if is_editing:
                # Editing mode - yellow/orange border
                pygame.draw.rect(self.screen, (50, 50, 65), 
                               (input_x, input_y, input_width, input_height), border_radius=6)
                pygame.draw.rect(self.screen, (255, 200, 100), 
                               (input_x, input_y, input_width, input_height), 2, border_radius=6)
                # Show typed text with cursor
                display_text = self.input_text + "|"
                val_color = (255, 255, 255)
            else:
                # Normal mode
                bg_color = (60, 65, 80) if is_selected else (45, 48, 60)
                pygame.draw.rect(self.screen, bg_color, 
                               (input_x, input_y, input_width, input_height), border_radius=6)
                if is_selected:
                    pygame.draw.rect(self.screen, (100, 150, 255), 
                                   (input_x, input_y, input_width, input_height), 1, border_radius=6)
                # Show current value
                current_val = self.settings[config['key']]
                display_text = str(int(current_val))
                val_color = (255, 255, 255) if is_selected else (160, 160, 170)
            
            # Value text centered in input box
            val_text = value_font.render(display_text, True, val_color)
            val_rect = val_text.get_rect(center=(input_x + input_width // 2, input_y + input_height // 2))
            self.screen.blit(val_text, val_rect)
            
            # Range hint
            range_font = pygame.font.Font(None, 22)
            range_text = range_font.render(f"({config['min']}-{config['max']})", True, (100, 100, 120))
            range_rect = range_text.get_rect(midleft=(input_x + input_width + 10, input_y + input_height // 2))
            self.screen.blit(range_text, range_rect)
        
        # Instructions at bottom
        instr_font = pygame.font.Font(None, 26)
        if self.editing_setting:
            instructions = "Type value → Enter to confirm → Esc to cancel"
        else:
            instructions = "↑/↓ Navigate   Enter to edit   R Reset   Tab/Esc Close"
        
        instr_text = instr_font.render(instructions, True, (140, 140, 160))
        instr_rect = instr_text.get_rect(midbottom=(self.window_width // 2, menu_y + menu_height - 20))
        self.screen.blit(instr_text, instr_rect)
        
    def draw_controls(self):
        """Draw control hints at bottom of screen."""
        if self.mode == GameMode.EDIT:
            controls = [
                "[1/2/3/4] Brush (R/P/S/Random)  |  [Click] Place  |  [Shift+Click] Cluster  |  "
                "[Right Click] Delete  |  [Scroll/+/-] Count",
                "[Space] Run  |  [Tab] Settings  |  [H] Hide UI  |  [A] Auto Mode  |  [C] Clear  |  [N] Random  |  [Esc] Quit"
            ]
        else:
            controls = [
                "[Space] Pause  |  [R] Restart  |  [Tab] Settings  |  [H] Hide UI  |  [A] Auto Mode  |  [C] Clear  |  [Esc] Quit"
            ]
            
        padding = 15
        y = self.window_height - padding
        
        for line in reversed(controls):
            text = self.font_controls.render(line, True, COLOR_TEXT_DIM)
            text_rect = text.get_rect(midbottom=(self.window_width // 2, y))
            
            # Background
            bg_rect = text_rect.inflate(20, 8)
            pygame.draw.rect(self.screen, (25, 25, 35, 200), bg_rect, border_radius=5)
            
            self.screen.blit(text, text_rect)
            y -= 30


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def list_audio_devices():
    pygame.init()
    try:
        import pygame._sdl2.audio as sdl_audio
        print("Playback devices:")
        for name in sdl_audio.get_audio_device_names(False):
            print(f"  {name}")
        print("Capture devices:")
        for name in sdl_audio.get_audio_device_names(True):
            print(f"  {name}")
    finally:
        pygame.quit()


def parse_args():
    parser = argparse.ArgumentParser(description="Rock Paper Scissors Bouncer")
    parser.add_argument("--stream", action="store_true", help="Run OBS-ready vertical stream mode")
    parser.add_argument("--preset", choices=["720p", "1080p"], help="Stream resolution preset")
    parser.add_argument("--audio-device", help="Playback device name for game SFX")
    parser.add_argument("--no-audio", action="store_true", help="Disable SFX")
    parser.add_argument("--list-audio-devices", action="store_true", help="Print SDL audio devices and exit")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.list_audio_devices:
        list_audio_devices()
        sys.exit(0)

    config = load_stream_config()
    if args.stream:
        config["stream_mode"] = True
    if args.preset:
        config["preset"] = args.preset
    if args.audio_device:
        config.setdefault("audio", {})["device"] = args.audio_device
    if args.no_audio:
        config.setdefault("audio", {})["enabled"] = False

    game = Game(config=config, force_stream_mode=args.stream)
    game.run()

