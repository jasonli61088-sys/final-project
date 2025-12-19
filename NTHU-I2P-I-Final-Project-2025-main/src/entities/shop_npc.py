from __future__ import annotations
import pygame as pg
from typing import override

from .entity import Entity
from src.sprites import Sprite
from src.core import GameManager
from src.utils import GameSettings, Direction, Position, PositionCamera


class ShopNPC(Entity):
    """A stationary NPC that opens a shop interface when interacted with"""
    
    interaction_range: int
    is_player_nearby: bool
    interact_indicator: Sprite
    
    def __init__(
        self,
        x: float,
        y: float,
        game_manager: GameManager,
        facing: Direction = Direction.DOWN,
        interaction_range: int = 1
    ) -> None:
        super().__init__(x, y, game_manager)
        self.interaction_range = interaction_range
        self.is_player_nearby = False
        self._set_direction(facing)
        
        # Create interaction indicator (e.g., exclamation mark or similar)
        self.interact_indicator = Sprite("exclamation.png", (GameSettings.TILE_SIZE // 2, GameSettings.TILE_SIZE // 2))
        self.interact_indicator.update_pos(Position(
            x + GameSettings.TILE_SIZE // 4, 
            y - GameSettings.TILE_SIZE // 2
        ))
    
    def _set_direction(self, direction: Direction) -> None:
        """Set the NPC's facing direction"""
        self.direction = direction
        if direction == Direction.RIGHT:
            self.animation.switch("right")
        elif direction == Direction.LEFT:
            self.animation.switch("left")
        elif direction == Direction.DOWN:
            self.animation.switch("down")
        else:
            self.animation.switch("up")
    
    def check_player_nearby(self) -> bool:
        """Check if player is within interaction range"""
        if self.game_manager.player is None:
            return False
        
        player_pos = self.game_manager.player.position
        npc_pos = self.position
        
        # Calculate tile distance
        dx = abs(player_pos.x - npc_pos.x) / GameSettings.TILE_SIZE
        dy = abs(player_pos.y - npc_pos.y) / GameSettings.TILE_SIZE
        
        # Check if within interaction range (using Manhattan distance)
        return (dx + dy) <= self.interaction_range
    
    @override
    def update(self, dt: float) -> None:
        super().update(dt)
        self.is_player_nearby = self.check_player_nearby()
        
        # Update indicator position
        self.interact_indicator.update_pos(Position(
            self.position.x + GameSettings.TILE_SIZE // 4,
            self.position.y - GameSettings.TILE_SIZE // 2
        ))
    
    @override
    def draw(self, screen: pg.Surface, camera: PositionCamera) -> None:
        super().draw(screen, camera)
        
        # Draw interaction indicator if player is nearby
        if self.is_player_nearby:
            self.interact_indicator.draw(screen, camera)
    
    def to_dict(self) -> dict[str, object]:
        """Serialize shop NPC to dictionary"""
        data = super().to_dict()
        data["type"] = "shop"
        data["facing"] = self.direction.name
        data["interaction_range"] = self.interaction_range
        return data
    
    @classmethod
    def from_dict(cls, data: dict[str, object], game_manager: GameManager) -> ShopNPC:
        """Deserialize shop NPC from dictionary"""
        x = float(data["x"]) * GameSettings.TILE_SIZE
        y = float(data["y"]) * GameSettings.TILE_SIZE
        facing = Direction[data.get("facing", "DOWN")]
        interaction_range = int(data.get("interaction_range", 1))
        
        return cls(x, y, game_manager, facing, interaction_range)
