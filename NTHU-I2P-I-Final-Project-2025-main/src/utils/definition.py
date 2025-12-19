from pygame import Rect
from .settings import GameSettings
from dataclasses import dataclass
from enum import Enum
from typing import overload, TypedDict, Protocol

MouseBtn = int
Key = int

Direction = Enum('Direction', ['UP', 'DOWN', 'LEFT', 'RIGHT', 'NONE'])

@dataclass
class Position:
    x: float
    y: float
    
    def copy(self):
        return Position(self.x, self.y)
        
    def distance_to(self, other: "Position") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5
        
@dataclass
class PositionCamera:
    x: int
    y: int
    
    def copy(self):
        return PositionCamera(self.x, self.y)
        
    def to_tuple(self) -> tuple[int, int]:
        return (self.x, self.y)
        
    def transform_position(self, position: Position) -> tuple[int, int]:
        return (int(position.x) - self.x, int(position.y) - self.y)
        
    def transform_position_as_position(self, position: Position) -> Position:
        return Position(int(position.x) - self.x, int(position.y) - self.y)
        
    def transform_rect(self, rect: Rect) -> Rect:
        return Rect(rect.x - self.x, rect.y - self.y, rect.width, rect.height)

@dataclass
class Teleport:
    pos: Position
    destination: str
    target_x: int | None
    target_y: int | None
    
    @overload
    def __init__(self, x: int, y: int, destination: str, target_x: int | None = None, target_y: int | None = None) -> None: ...
    @overload
    def __init__(self, pos: Position, destination: str, target_x: int | None = None, target_y: int | None = None) -> None: ...

    def __init__(self, *args, **kwargs):
        target_x = kwargs.get('target_x')
        target_y = kwargs.get('target_y')
        if isinstance(args[0], Position):
            self.pos = args[0]
            self.destination = args[1]
            self.target_x = target_x if len(args) <= 2 else (args[2] if len(args) > 2 else None)
            self.target_y = target_y if len(args) <= 3 else (args[3] if len(args) > 3 else None)
        else:
            x, y, dest = args[0], args[1], args[2]
            self.pos = Position(x, y)
            self.destination = dest
            self.target_x = target_x if len(args) <= 3 else (args[3] if len(args) > 3 else None)
            self.target_y = target_y if len(args) <= 4 else (args[4] if len(args) > 4 else None)
    
    def to_dict(self):
        result = {
            "x": self.pos.x // GameSettings.TILE_SIZE,
            "y": self.pos.y // GameSettings.TILE_SIZE,
            "destination": self.destination
        }
        if self.target_x is not None:
            result["target_x"] = self.target_x
        if self.target_y is not None:
            result["target_y"] = self.target_y
        return result
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            data["x"] * GameSettings.TILE_SIZE,
            data["y"] * GameSettings.TILE_SIZE,
            data["destination"],
            target_x=data.get("target_x"),
            target_y=data.get("target_y")
        )
    
class Monster(TypedDict):
    name: str
    hp: int
    max_hp: int
    level: int
    sprite_path: str
    element: str
    exp: int  # Current experience points
    exp_to_next_level: int  # Experience needed for next level

class Item(TypedDict):
    name: str
    count: int
    sprite_path: str

# --- Simple Element system and effectiveness ---
class Element(Enum):
    NORMAL = "Normal"
    FIRE = "Fire"
    WATER = "Water"
    GRASS = "Grass"

_EFFECTIVENESS: dict[Element, set[Element]] = {
    Element.WATER: {Element.FIRE},
    Element.FIRE: {Element.GRASS},
    Element.GRASS: {Element.WATER},
}

def effectiveness_multiplier(attacker: str | Element, defender: str | Element) -> float:
    """Return damage multiplier based on simple strengths/weaknesses.
    - Strong: 2.0
    - Weak: 0.5
    - Neutral: 1.0
    Accepts string names; falls back to neutral if unknown.
    """
    try:
        a = attacker if isinstance(attacker, Element) else Element[attacker.upper()]
        d = defender if isinstance(defender, Element) else Element[defender.upper()]
    except Exception:
        return 1.0
    # strong case
    if d in _EFFECTIVENESS.get(a, set()):
        return 2.0
    # weak case (defender strong against attacker)
    if a in _EFFECTIVENESS.get(d, set()):
        return 0.5
    return 1.0


def calculate_exp_for_level(level: int) -> int:
    """Calculate total experience needed to reach a given level.
    Uses formula: exp_for_level = level * 5
    """
    return level * 5


def calculate_monster_stats(level: int, base_hp: int = 20) -> dict:
    """
    Calculate Pokemon stats based on level.
    Formula:
    - hp = base_hp + (level - 1) * 5
    - attack = 10 + (level - 1) * 1.5
    - defense = 8 + (level - 1) * 1.2
    """
    hp = base_hp + (level - 1) * 5
    attack = 10 + (level - 1) * 1.5
    defense = 8 + (level - 1) * 1.2
    return {"hp": int(hp), "max_hp": int(hp), "attack": attack, "defense": defense}


# Evolution system: maps sprite path to (evolution_level, evolved_sprite_path, evolved_name)
EVOLUTION_MAP = {
    "menu_sprites/menusprite1.png": (16, "menu_sprites/menusprite2.png", "Charizard"),
    "menu_sprites/menusprite2.png": (36, "menu_sprites/menusprite3.png", "Blastoise"),
    "menu_sprites/menusprite7.png": (16, "menu_sprites/menusprite8.png", "Pidgey"),
    "menu_sprites/menusprite8.png": (36, "menu_sprites/menusprite9.png", "Zubat"),
    "menu_sprites/menusprite12.png": (16, "menu_sprites/menusprite13.png", "Eevee"),
    "menu_sprites/menusprite13.png": (36, "menu_sprites/menusprite14.png", "Jigglypuff"),
    "menu_sprites/menusprite15.png": (16, "menu_sprites/menusprite16.png", "Psyduck"),
}


def check_evolution(sprite_path: str, current_level: int) -> tuple[str, str] | None:
    """
    Check if a Pokemon should evolve based on its sprite and level.
    Returns (new_sprite_path, new_name) if evolution occurs, otherwise None.
    """
    if sprite_path in EVOLUTION_MAP:
        evolution_level, evolved_sprite, evolved_name = EVOLUTION_MAP[sprite_path]
        if current_level >= evolution_level:
            return (evolved_sprite, evolved_name)
    return None