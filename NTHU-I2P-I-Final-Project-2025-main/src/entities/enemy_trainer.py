from __future__ import annotations
import pygame
from enum import Enum
import random
from dataclasses import dataclass
from typing import override

from .entity import Entity
from src.sprites import Sprite
from src.core import GameManager
from src.core.services import input_manager, scene_manager
from src.utils import GameSettings, Direction, Position, PositionCamera


class EnemyTrainerClassification(Enum):
    STATIONARY = "stationary"

@dataclass
class IdleMovement:
    def update(self, enemy: "EnemyTrainer", dt: float) -> None:
        return

class EnemyTrainer(Entity):
    classification: EnemyTrainerClassification
    max_tiles: int | None
    _movement: IdleMovement
    warning_sign: Sprite
    detected: bool
    los_direction: Direction
    element: str

    @override
    def __init__(
        self,
        x: float,
        y: float,
        game_manager: GameManager,
        classification: EnemyTrainerClassification = EnemyTrainerClassification.STATIONARY,
        max_tiles: int | None = 2,
        facing: Direction | None = None,
    ) -> None:
        super().__init__(x, y, game_manager)
        self.classification = classification
        self.max_tiles = max_tiles
        if classification == EnemyTrainerClassification.STATIONARY:
            self._movement = IdleMovement()
            if facing is None:
                raise ValueError("Idle EnemyTrainer requires a 'facing' Direction at instantiation")
            self._set_direction(facing)
        else:
            raise ValueError("Invalid classification")
        self.warning_sign = Sprite("exclamation.png", (GameSettings.TILE_SIZE // 2, GameSettings.TILE_SIZE // 2))
        self.warning_sign.update_pos(Position(x + GameSettings.TILE_SIZE // 4, y - GameSettings.TILE_SIZE // 2))
        self.detected = False
        # default element for trainer's leading monster
        self.element = "Fire"

    @override
    def update(self, dt: float) -> None:
        self._movement.update(self, dt)
        self._has_los_to_player()
        if self.detected and input_manager.key_pressed(pygame.K_SPACE):
            # Start a battle: store the target on the scene_manager and switch to battle scene
            try:
                # Assign a random monster (sprite1~16) with basic stats before battle
                self._assign_random_monster()
                setattr(scene_manager, "battle_target", self)
                scene_manager.change_scene("battle")
            except Exception:
                pass
        self.animation.update_pos(self.position)

    @override
    def draw(self, screen: pygame.Surface, camera: PositionCamera) -> None:
        super().draw(screen, camera)
        if self.detected:
            self.warning_sign.draw(screen, camera)
        if GameSettings.DRAW_HITBOXES:
            los_rect = self._get_los_rect()
            if los_rect is not None:
                pygame.draw.rect(screen, (255, 255, 0), camera.transform_rect(los_rect), 1)

    def _set_direction(self, direction: Direction) -> None:
        self.direction = direction
        if direction == Direction.RIGHT:
            self.animation.switch("right")
        elif direction == Direction.LEFT:
            self.animation.switch("left")
        elif direction == Direction.DOWN:
            self.animation.switch("down")
        else:
            self.animation.switch("up")
        self.los_direction = self.direction

    def _get_los_rect(self) -> pygame.Rect | None:
        # Create a simple rectangular LOS in the facing direction with length = max_tiles
        if self.max_tiles is None:
            return None
        x = int(self.position.x)
        y = int(self.position.y)
        tile = GameSettings.TILE_SIZE
        if self.los_direction == Direction.RIGHT:
            return pygame.Rect(x + tile, y, self.max_tiles * tile, tile)
        if self.los_direction == Direction.LEFT:
            return pygame.Rect(x - self.max_tiles * tile, y, self.max_tiles * tile, tile)
        if self.los_direction == Direction.DOWN:
            return pygame.Rect(x, y + tile, tile, self.max_tiles * tile)
        if self.los_direction == Direction.UP:
            return pygame.Rect(x, y - self.max_tiles * tile, tile, self.max_tiles * tile)
        return None

    def _has_los_to_player(self) -> None:
        player = self.game_manager.player
        if player is None:
            self.detected = False
            return
        los_rect = self._get_los_rect()
        if los_rect is None:
            self.detected = False
            return
        # Simple LOS: check if player's hitbox intersects LOS rect
        try:
            player_rect = player.animation.rect
            if player_rect.colliderect(los_rect):
                self.detected = True
                # update warning sign position above head
                self.warning_sign.update_pos(Position(self.position.x + GameSettings.TILE_SIZE // 4, self.position.y - GameSettings.TILE_SIZE // 2))
                return
        except Exception:
            pass
        self.detected = False

    @classmethod
    @override
    def from_dict(cls, data: dict, game_manager: GameManager) -> "EnemyTrainer":
        classification = EnemyTrainerClassification(data.get("classification", "stationary"))
        max_tiles = data.get("max_tiles")
        facing_val = data.get("facing")
        facing: Direction | None = None
        if facing_val is not None:
            if isinstance(facing_val, str):
                facing = Direction[facing_val]
            elif isinstance(facing_val, Direction):
                facing = facing_val
        if facing is None and classification == EnemyTrainerClassification.STATIONARY:
            facing = Direction.DOWN
        return cls(
            data["x"] * GameSettings.TILE_SIZE,
            data["y"] * GameSettings.TILE_SIZE,
            game_manager,
            classification,
            max_tiles,
            facing,
        )

    @override
    def to_dict(self) -> dict[str, object]:
        base: dict[str, object] = super().to_dict()
        base["classification"] = self.classification.value
        base["facing"] = self.direction.name
        base["max_tiles"] = self.max_tiles
        base["element"] = self.element
        return base

    def _assign_random_monster(self) -> None:
        """Assign a random Pokemon sprite (1-16) and simple stats for battle.
        This sets dynamic attributes consumed by BattleScene: sprite_path, name,
        level, hp, max_hp, attack, element, exp, exp_to_next_level.
        """
        try:
            idx = random.randint(1, 16)
            sprite_path = f"sprites/sprite{idx}.png"
            name = f"Sprite{idx}"
            
            # Tier-based level assignment
            tier1 = {1, 4, 5, 6, 7, 10, 11, 12, 15}
            tier2 = {2, 8, 13, 16}
            tier3 = {3, 9, 14}
            
            if idx in tier1:
                level = random.randint(6, 15)
            elif idx in tier2:
                level = random.randint(16, 35)
            elif idx in tier3:
                level = random.randint(36, 50)
            else:
                level = random.randint(6, 15)  # Fallback
            
            # Scale HP and attack based on level with exact formulas
            # HP formula: 5 * level + 15
            max_hp = round(5 * level + 15)
            
            # Attack formula (piecewise linear):
            # Levels 6-16: slope = 5/9 from (7,10) to (16,15)
            # Levels 16+: slope = 0.5 from (16,15) to (36,25)
            if level <= 16:
                attack = round(10 + (level - 7) * (5 / 9))
            else:
                attack = round(15 + (level - 16) * 0.5)
            
            # Map index to element to align with BattleScene's logic
            grass = {1, 2, 3, 15, 16}
            fire = {4, 5, 7, 8, 9}
            water = {6, 10, 11, 12, 13, 14}
            if idx in grass:
                element = "Grass"
            elif idx in fire:
                element = "Fire"
            elif idx in water:
                element = "Water"
            else:
                element = "Normal"

            # Assign on self for BattleScene to read
            self.sprite_path = sprite_path
            self.name = name
            self.level = level
            self.max_hp = max_hp
            self.hp = max_hp
            self.attack = attack
            self.element = element
            # Wild-like progression fields
            self.exp = 0
            self.exp_to_next_level = level ** 2 * 10
            # Provide a dict with the same schema used for wild monsters
            self.monster_data = {
                "name": name,
                "hp": max_hp,
                "max_hp": max_hp,
                "level": level,
                "sprite_path": sprite_path,
                "element": element,
                "exp": 0,
                "exp_to_next_level": self.exp_to_next_level,
                "attack": attack,
            }
        except Exception:
            # Fallback to a reasonable default
            try:
                self.sprite_path = "sprites/sprite10.png"
                self.name = "Sprite10"
                self.level = 5
                self.max_hp = 80
                self.hp = 80
                self.attack = 10
                self.element = "Water"
                self.exp = 0
                self.exp_to_next_level = self.level ** 2 * 10
                self.monster_data = {
                    "name": self.name,
                    "hp": self.max_hp,
                    "max_hp": self.max_hp,
                    "level": self.level,
                    "sprite_path": self.sprite_path,
                    "element": self.element,
                    "exp": 0,
                    "exp_to_next_level": self.exp_to_next_level,
                    "attack": self.attack,
                }
            except Exception:
                pass