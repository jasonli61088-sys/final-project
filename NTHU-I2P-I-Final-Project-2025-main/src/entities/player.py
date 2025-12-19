from __future__ import annotations
import pygame as pg
from .entity import Entity
from src.core.services import input_manager
from src.core.services import scene_manager
from src.utils import Position, PositionCamera, GameSettings, Logger, Direction
from src.core import GameManager
import math
from typing import override
import random
from types import SimpleNamespace

class Player(Entity):
    speed: float = 4.0 * GameSettings.TILE_SIZE
    game_manager: GameManager

    def __init__(self, x: float, y: float, game_manager: GameManager) -> None:
        super().__init__(x, y, game_manager)
        # track whether player was on a bush in the previous frame to avoid retriggering
        self._on_bush: bool = False
        # teleport cooldown timer to prevent being trapped in loops
        self._teleport_cooldown: float = 0.0
        self.is_moving: bool = False

    @override
    def update(self, dt: float) -> None:
        dis = Position(0, 0)
        '''
        [TODO HACKATHON 2]
        Calculate the distance change, and then normalize the distance
        
        [TODO HACKATHON 4]
        Check if there is collision, if so try to make the movement smooth
        Hint #1 : use entity.py _snap_to_grid function or create a similar function
        Hint #2 : Beware of glitchy teleportation, you must do
                    1. Update X
                    2. If collide, snap to grid
                    3. Update Y
                    4. If collide, snap to grid
                  instead of update both x, y, then snap to grid
        
        if input_manager.key_down(pg.K_LEFT) or input_manager.key_down(pg.K_a):
            dis.x -= ...
        if input_manager.key_down(pg.K_RIGHT) or input_manager.key_down(pg.K_d):
            dis.x += ...
        if input_manager.key_down(pg.K_UP) or input_manager.key_down(pg.K_w):
            dis.y -= ...
        if input_manager.key_down(pg.K_DOWN) or input_manager.key_down(pg.K_s):
            dis.y += ...
        
        self.position = ...
        '''
        
        # Gate manual input when controls are locked (e.g., chat open or auto-navigation)
        controls_locked = getattr(self.game_manager, "controls_locked", False)
        # Movement input (WASD + arrows) only when not locked
        if not controls_locked:
            if input_manager.key_down(pg.K_LEFT) or input_manager.key_down(pg.K_a):
                dis.x -= 1
            if input_manager.key_down(pg.K_RIGHT) or input_manager.key_down(pg.K_d):
                dis.x += 1
            if input_manager.key_down(pg.K_UP) or input_manager.key_down(pg.K_w):
                dis.y -= 1
            if input_manager.key_down(pg.K_DOWN) or input_manager.key_down(pg.K_s):
                dis.y += 1

            # Update facing direction according to raw input vector (prefer horizontal when diagonal)
            if dis.x > 0:
                self.direction = Direction.RIGHT
                self.animation.switch("right")
            elif dis.x < 0:
                self.direction = Direction.LEFT
                self.animation.switch("left")
            elif dis.y > 0:
                self.direction = Direction.DOWN
                self.animation.switch("down")
            elif dis.y < 0:
                self.direction = Direction.UP
                self.animation.switch("up")
        # Normalize movement so diagonal isn't faster
        dx = dy = 0.0
        if not controls_locked:
            self.is_moving = bool(dis.x != 0 or dis.y != 0)
        if self.is_moving:
            mag = math.hypot(dis.x, dis.y)
            if mag != 0:
                nx = dis.x / mag
                ny = dis.y / mag
                # Movement amount in pixels for this frame
                dx = nx * self.speed * dt
                dy = ny * self.speed * dt

        # Move X then Y separately and check collisions
        if dx != 0.0:
            self.position.x += dx
            # update animation rect for collision check
            self.animation.update_pos(self.position)
            if self.game_manager.check_collision(self.animation.rect):
                # revert X movement on collision
                self.position.x -= dx
                self.animation.update_pos(self.position)

        if dy != 0.0:
            self.position.y += dy
            self.animation.update_pos(self.position)
            if self.game_manager.check_collision(self.animation.rect):
                # revert Y movement on collision
                self.position.y -= dy
                self.animation.update_pos(self.position)

        # Update teleport cooldown
        if self._teleport_cooldown > 0:
            self._teleport_cooldown -= dt
        
        # Check teleportation (only if cooldown has expired)
        if self._teleport_cooldown <= 0:
            tp = self.game_manager.current_map.check_teleport(self.position)
            if tp:
                dest = tp.destination
                self.game_manager.switch_map(dest, tp.target_x, tp.target_y)
                # Set 1 second cooldown after teleporting
                self._teleport_cooldown = 1.0
        # Check for stepping into a PokemonBush tile: start a wild battle when entering
        try:
            in_bush = self.game_manager.current_map.is_pokemon_bush_at(self.position)
            if in_bush and not self._on_bush:
                # Just entered a bush tile — spawn a random wild pokemon and start battle
                candidates = [
                    {"name": "Pikachu", "level": 7, "hp": 50, "max_hp": 50, "attack": 10, "sprite_path": "menu_sprites/menusprite1.png", "element": "Grass", "exp": 0, "exp_to_next_level": 40},
                    {"name": "Charizard", "level": 36, "hp": 195, "max_hp": 195, "attack": 25, "sprite_path": "menu_sprites/menusprite2.png", "element": "Grass", "exp": 0, "exp_to_next_level": 185},
                    {"name": "Blastoise", "level": 36, "hp": 195, "max_hp": 195, "attack": 25, "sprite_path": "menu_sprites/menusprite3.png", "element": "Grass", "exp": 0, "exp_to_next_level": 185},
                    {"name": "Venusaur", "level": 7, "hp": 50, "max_hp": 50, "attack": 10, "sprite_path": "menu_sprites/menusprite4.png", "element": "Fire", "exp": 0, "exp_to_next_level": 40},
                    {"name": "Gengar", "level": 7, "hp": 50, "max_hp": 50, "attack": 10, "sprite_path": "menu_sprites/menusprite5.png", "element": "Fire", "exp": 0, "exp_to_next_level": 40},
                    {"name": "Dragonite", "level": 7, "hp": 50, "max_hp": 50, "attack": 10, "sprite_path": "menu_sprites/menusprite6.png", "element": "Water", "exp": 0, "exp_to_next_level": 40},
                    {"name": "Rattata", "level": 7, "hp": 50, "max_hp": 50, "attack": 10, "sprite_path": "menu_sprites/menusprite7.png", "element": "Fire", "exp": 0, "exp_to_next_level": 40},
                    {"name": "Pidgey", "level": 16, "hp": 95, "max_hp": 95, "attack": 15, "sprite_path": "menu_sprites/menusprite8.png", "element": "Fire", "exp": 0, "exp_to_next_level": 85},
                    {"name": "Zubat", "level": 36, "hp": 195, "max_hp": 195, "attack": 25, "sprite_path": "menu_sprites/menusprite9.png", "element": "Fire", "exp": 0, "exp_to_next_level": 185},
                    {"name": "Caterpie", "level": 7, "hp": 50, "max_hp": 50, "attack": 10, "sprite_path": "menu_sprites/menusprite10.png", "element": "Water", "exp": 0, "exp_to_next_level": 40},
                    {"name": "Oddish", "level": 7, "hp": 50, "max_hp": 50, "attack": 10, "sprite_path": "menu_sprites/menusprite11.png", "element": "Water", "exp": 0, "exp_to_next_level": 40},
                    {"name": "Sandshrew", "level": 7, "hp": 50, "max_hp": 50, "attack": 10, "sprite_path": "menu_sprites/menusprite12.png", "element": "Water", "exp": 0, "exp_to_next_level": 40},
                    {"name": "Eevee", "level": 16, "hp": 95, "max_hp": 95, "attack": 15, "sprite_path": "menu_sprites/menusprite13.png", "element": "Water", "exp": 0, "exp_to_next_level": 85},
                    {"name": "Jigglypuff", "level": 36, "hp": 195, "max_hp": 195, "attack": 25, "sprite_path": "menu_sprites/menusprite14.png", "element": "Water", "exp": 0, "exp_to_next_level": 185},
                    {"name": "Meowth", "level": 7, "hp": 50, "max_hp": 50, "attack": 10, "sprite_path": "menu_sprites/menusprite15.png", "element": "Grass", "exp": 0, "exp_to_next_level": 40},
                    {"name": "Psyduck", "level": 16, "hp": 95, "max_hp": 95, "attack": 15, "sprite_path": "menu_sprites/menusprite16.png", "element": "Grass", "exp": 0, "exp_to_next_level": 85},
                ]
                wild = random.choice(candidates)
                # Create a lightweight battle target object that BattleScene can read
                target = SimpleNamespace()
                target.game_manager = self.game_manager
                target.hp = wild.get("hp", 10)
                target.max_hp = wild.get("max_hp", target.hp)
                target.sprite_path = wild.get("sprite_path")
                target.name = wild.get("name")
                target.level = wild.get("level", 1)
                target.attack = wild.get("attack", 8)
                # mark as wild encounter target
                target.is_wild = True
                # assign battle target to scene_manager and switch to battle
                try:
                    setattr(scene_manager, "battle_target", target)
                    scene_manager.change_scene("battle")
                except Exception:
                    Logger.warning("Failed to start wild battle via scene_manager")
                self._on_bush = True
            elif not in_bush:
                # left bush
                self._on_bush = False
        except Exception:
            pass
                
        super().update(dt)

    @override
    def draw(self, screen: pg.Surface, camera: PositionCamera) -> None:
        super().draw(screen, camera)
        
    @override
    def to_dict(self) -> dict[str, object]:
        return super().to_dict()
    
    @classmethod
    @override
    def from_dict(cls, data: dict[str, object], game_manager: GameManager) -> Player:
        return cls(data["x"] * GameSettings.TILE_SIZE, data["y"] * GameSettings.TILE_SIZE, game_manager)

