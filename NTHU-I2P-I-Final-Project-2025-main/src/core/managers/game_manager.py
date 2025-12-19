from __future__ import annotations
from src.utils import Logger, GameSettings, Position, Teleport
import json, os
import pygame as pg
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.maps.map import Map
    from src.entities.player import Player
    from src.entities.enemy_trainer import EnemyTrainer
    from src.data.bag import Bag

class GameManager:
    # Entities
    player: Player | None
    enemy_trainers: dict[str, list[EnemyTrainer]]
    shop_npcs: dict[str, list]
    bag: "Bag"
    
    # Map properties
    current_map_key: str
    maps: dict[str, Map]
    
    # Changing Scene properties
    should_change_scene: bool
    next_map: str
    
    def __init__(self, maps: dict[str, Map], start_map: str, 
                 player: Player | None,
                 enemy_trainers: dict[str, list[EnemyTrainer]], 
                 bag: Bag | None = None):
                     
        from src.data.bag import Bag
        # Game Properties
        self.maps = maps
        self.current_map_key = start_map
        self.player = player
        self.enemy_trainers = enemy_trainers
        self.shop_npcs = {}  # Initialize shop NPCs dictionary
        self.bag = bag if bag is not None else Bag([], [])
        # Runtime control flag: when True, player input (WASD/arrows) is ignored
        # Used by scenes to disable movement while chatting or during auto-navigation
        self.controls_locked: bool = False

        # Player spawn positions per map (pixel coordinates)
        # Ensure this always exists so save/load code can rely on it
        self.player_spawns: dict[str, Position] = {}
        
        # Check If you should change scene
        self.should_change_scene = False
        self.next_map = ""
        
    @property
    def current_map(self) -> Map:
        return self.maps[self.current_map_key]
        
    @property
    def current_enemy_trainers(self) -> list[EnemyTrainer]:
        return self.enemy_trainers[self.current_map_key]
    
    @property
    def current_shop_npcs(self) -> list:
        return self.shop_npcs.get(self.current_map_key, [])
        
    @property
    def current_teleporter(self) -> list[Teleport]:
        return self.maps[self.current_map_key].teleporters
    
    def switch_map(self, target: str, target_x: int | None = None, target_y: int | None = None) -> None:
        if target not in self.maps:
            Logger.warning(f"Map '{target}' not loaded; cannot switch.")
            return
        
        self.next_map = target
        self.next_map_target_x = target_x
        self.next_map_target_y = target_y
        self.should_change_scene = True
            
    def try_switch_map(self) -> None:
        if self.should_change_scene:
            self.current_map_key = self.next_map
            self.next_map = ""
            self.should_change_scene = False
            if self.player:
                # Use explicit target coordinates if provided; otherwise use map spawn
                if hasattr(self, 'next_map_target_x') and self.next_map_target_x is not None:
                    target_x = self.next_map_target_x * GameSettings.TILE_SIZE
                    target_y = self.next_map_target_y * GameSettings.TILE_SIZE
                    self.player.position = Position(target_x, target_y)
                    self.next_map_target_x = None
                    self.next_map_target_y = None
                else:
                    target_spawn = self.maps[self.current_map_key].spawn
                    self.player.position = Position(target_spawn.x, target_spawn.y)
            
    def check_collision(self, rect: pg.Rect) -> bool:
        if self.maps[self.current_map_key].check_collision(rect):
            return True
        for entity in self.enemy_trainers[self.current_map_key]:
            if rect.colliderect(entity.animation.rect):
                return True
        
        return False
        
    def save(self, path: str) -> None:
        try:
            with open(path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
            Logger.info(f"Game saved to {path}")
        except Exception as e:
            Logger.warning(f"Failed to save game: {e}")
             
    @classmethod
    def load(cls, path: str) -> "GameManager | None":
        if not os.path.exists(path):
            Logger.warning(f"No file found: {path}, ignoring load function")
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            Logger.warning(f"Save file '{path}' is empty or corrupted (JSON decode error)")
            return None
        except Exception as e:
            Logger.warning(f"Failed to read save file '{path}': {e}")
            return None
        try:
            return cls.from_dict(data)
        except Exception as e:
            Logger.warning(f"Failed to construct GameManager from save data: {e}")
            return None

    def to_dict(self) -> dict[str, object]:
        map_blocks: list[dict[str, object]] = []
        for key, m in self.maps.items():
            # Start from the map's own serialization (which uses its internal spawn)
            block = m.to_dict()
            block["enemy_trainers"] = [t.to_dict() for t in self.enemy_trainers.get(key, [])]
            block["shop_npcs"] = [npc.to_dict() for npc in self.shop_npcs.get(key, [])]
            # Do not override the map's spawn with the player's current position.
            # This keeps teleporter destinations and outdoor returns stable.
            map_blocks.append(block)
        return {
            "map": map_blocks,
            "current_map": self.current_map_key,
            "player": self.player.to_dict() if self.player is not None else None,
            "bag": self.bag.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "GameManager":
        from src.maps.map import Map
        from src.entities.player import Player
        from src.entities.enemy_trainer import EnemyTrainer
        from src.data.bag import Bag
        
        Logger.info("Loading maps")
        maps_data = data["map"]
        maps: dict[str, Map] = {}
        player_spawns: dict[str, Position] = {}
        trainers: dict[str, list[EnemyTrainer]] = {}

        for entry in maps_data:
            path = entry["path"]
            maps[path] = Map.from_dict(entry)
            sp = entry.get("player")
            if sp:
                player_spawns[path] = Position(
                    sp["x"] * GameSettings.TILE_SIZE,
                    sp["y"] * GameSettings.TILE_SIZE
                )
        current_map = data["current_map"]
        gm = cls(
            maps, current_map,
            None, # Player
            trainers,
            bag=None
        )
        gm.current_map_key = current_map
        # Assign parsed player spawn points so save/serialize can access them
        gm.player_spawns = player_spawns
        
        Logger.info("Loading enemy trainers")
        for m in data["map"]:
            raw_data = m["enemy_trainers"]
            gm.enemy_trainers[m["path"]] = [EnemyTrainer.from_dict(t, gm) for t in raw_data]
        
        Logger.info("Loading shop NPCs")
        from src.entities.shop_npc import ShopNPC
        for m in data["map"]:
            shop_data = m.get("shop_npcs", [])
            gm.shop_npcs[m["path"]] = [ShopNPC.from_dict(npc, gm) for npc in shop_data]
        
        Logger.info("Loading Player")
        if data.get("player"):
            gm.player = Player.from_dict(data["player"], gm)
        
        Logger.info("Loading bag")
        from src.data.bag import Bag as _Bag
        gm.bag = Bag.from_dict(data.get("bag", {})) if data.get("bag") else _Bag([], [])

        return gm