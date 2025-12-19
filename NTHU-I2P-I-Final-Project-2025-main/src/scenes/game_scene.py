import pygame as pg
import threading
import time

from src.scenes.scene import Scene
from src.core import GameManager, OnlineManager
from src.utils import Logger, PositionCamera, GameSettings, Position
from src.core.services import sound_manager, scene_manager
from src.sprites import Sprite, Animation
from src.interface.components import Button
from src.scenes.backpack_overlay import BackpackOverlay
from src.scenes.shop_overlay import ShopOverlay
from typing import override

class GameScene(Scene):
    # Helper to load images for backpack
    def _get_image(self, rel_path, size=(64,64)):
        import os
        from src.core.services import resource_manager
        # Try all asset folders
        asset_dirs = ["sprites/", "menu_sprites/", "ingame_ui/", "character/", "attack/", "backgrounds/", "UI/"]
        for d in asset_dirs:
            full = os.path.join(d, rel_path)
            try:
                img = resource_manager.get_image(full)
                if img:
                    return pg.transform.scale(img, size)
            except Exception:
                continue
        # fallback: try rel_path directly
        try:
            img = resource_manager.get_image(rel_path)
            if img:
                return pg.transform.scale(img, size)
        except Exception:
            pass
        # fallback: blank
        surf = pg.Surface(size)
        surf.fill((200,200,200))
        return surf
    game_manager: GameManager
    online_manager: OnlineManager | None
    sprite_online: Sprite
    online_sprites: dict[int, Animation]
    # Navigate overlay state and UI
    navigate_active: bool
    # Auto-navigation state
    is_navigating: bool
    navigation_path: list[tuple[int, int]]
    current_nav_target: tuple[int, int] | None
    nav_teleport_pending: tuple[str, int, int] | None  # (target_map, target_x, target_y)
    
    def __init__(self):
        super().__init__()
        # Game Manager
        self.backpack_active = False
        # Try primary save, fallback to backup save if primary missing/invalid
        manager = GameManager.load("saves/game0.json")
        if manager is None:
            Logger.warning("Primary save 'saves/game0.json' failed to load; trying backup 'saves/backup.json'.")
            try:
                # Copy backup over primary save and retry
                with open("saves/backup.json", "r", encoding="utf-8") as bf:
                    data = bf.read()
                with open("saves/game0.json", "w", encoding="utf-8") as pf:
                    pf.write(data)
                manager = GameManager.load("saves/game0.json")
            except Exception as e:
                Logger.error(f"Failed to recover save from backup: {e}")

        if manager is None:
            Logger.error("Failed to load game manager. Please check saves/game0.json and all required assets/maps.")
            from src.core.services import scene_manager
            # 回到主選單
            self.game_manager = None
            scene_manager.change_scene("menu")
            return

        self.game_manager = manager
        # Backpack overlay helper (handles scrolling, rendering of monsters/items)
        self.backpack_overlay = BackpackOverlay(self.game_manager)
        # Shop overlay
        self.shop_overlay = ShopOverlay(self.game_manager)
        self.shop_active = False
        # Minimap
        self.minimap_size = 150  # Size of minimap in pixels
        self.minimap_x = 10  # Top-left corner x
        self.minimap_y = 10  # Top-left corner y
        # If this entry is a fresh start (from main menu), place the player at the
        # current map's spawn instead of any saved position.
        try:
            from src.core.services import scene_manager
            if getattr(scene_manager, "start_fresh_game", False):
                if self.game_manager.player is not None:
                    spawn = self.game_manager.current_map.spawn
                    self.game_manager.player.position.x = spawn.x
                    self.game_manager.player.position.y = spawn.y
                    # update animation rect to match new position
                    self.game_manager.player.animation.update_pos(self.game_manager.player.position)
                # Reset bag to single starter monster when starting a fresh game
                try:
                    starter = {
                        "name": "Pikachu",
                        "hp": 85,
                        "max_hp": 100,
                        "level": 25,
                        "sprite_path": "menu_sprites/menusprite1.png"
                    }
                    # Replace monsters list with only the starter
                    try:
                        self.game_manager.bag._monsters_data = [starter]
                    except Exception:
                        # fallback: create a new Bag instance
                        from src.data.bag import Bag
                        self.game_manager.bag = Bag([starter], self.game_manager.bag._items_data if getattr(self.game_manager.bag, '_items_data', None) is not None else [])
                    # Do NOT persist reset to disk here; keep reset in-memory only
                except Exception:
                    pass
                # Clear the flag so subsequent entries are normal
                setattr(scene_manager, "start_fresh_game", False)
            # Prevent immediate wild encounters on load: mark player as already "on bush"
            try:
                if self.game_manager.player is not None:
                    # set internal flag so entering the scene doesn't auto-trigger a wild battle
                    setattr(self.game_manager.player, "_on_bush", True)
            except Exception:
                pass
        except Exception:
            pass
        
        # Online Manager
        if GameSettings.IS_ONLINE:
            self.online_manager = OnlineManager()
        else:
            self.online_manager = None
        self.sprite_online = Sprite("ingame_ui/options1.png", (GameSettings.TILE_SIZE, GameSettings.TILE_SIZE))
        self.online_sprites = {}
        # Chat overlay state
        self.chat_active = False
        self.chat_text = ""
        self.chat_messages: list[dict] = []
        self.chat_font = pg.font.SysFont("arial", 18)
        
        # Stable player ID mapping for chat display (maps real ID to display ID 0, 1, 2...)
        self._player_id_map: dict[int, int] = {}
        self._next_display_id = 0
        # Backpack overlay button (top-right corner)
        bx = GameSettings.SCREEN_WIDTH - 60
        by = 10
        self.backpack_button = Button(
            "UI/button_backpack.png", "UI/button_backpack_hover.png",
            bx, by, 48, 48,
            lambda: setattr(self, "backpack_active", True)
        )
        # Settings overlay state
        self.overlay_active = False
        sbx = bx - 56
        self.settings_button = Button(
            "UI/button_setting.png", "UI/button_setting_hover.png",
            sbx, by, 48, 48,
            lambda: setattr(self, "overlay_active", True)
        )
        # Navigate button (left of settings)
        nbx = sbx - 56
        self.navigate_active = False
        self.navigate_button = Button(
            "UI/button_shop.png", "UI/button_shop_hover.png",
            nbx, by, 48, 48,
            lambda: setattr(self, "navigate_active", True)
        )
        # Settings overlay back button
        self.overlay_back_button = Button(
            "UI/button_x.png", "UI/button_x_hover.png",
            GameSettings.SCREEN_WIDTH // 2 + 250 - 48, GameSettings.SCREEN_HEIGHT // 2 - 200, 48, 48,
            self._handle_close_overlay
        )
        # Settings overlay Save / Load / Back buttons (positions set when drawing overlay)
        # Create with placeholder positions; we'll position them relative to the panel when drawing
        # Use square buttons: height = width (use current width as side length)
        self.overlay_save_button = Button(
            "UI/button_save.png", "UI/button_save_hover.png",
            0, 0, 70, 70,
            self._overlay_save
        )
        self.overlay_load_button = Button(
            "UI/button_load.png", "UI/button_load_hover.png",
            0, 0, 70, 70,
            self._overlay_load
        )
        self.overlay_close_button = Button(
            "UI/button_back.png", "UI/button_back_hover.png",
            0, 0, 70, 70,
            self._overlay_back
        )

        # Navigate overlay components
        # Format: (display_name, map_file, target_x_tile, target_y_tile)
        # If target coords are None, use map spawn
        self._navigate_locations: list[tuple[str, str, int | None, int | None]] = [
            # Attachment 1: Start position (16,30)
            ("Start", "map.tmx", 16, 30),
            # Attachment 2: gym interior landing spot (gym.tmx) - only in gym and map
            ("Gym", "gym.tmx", 12, 15),
            # Attachment 3: shop area near NPC (new_map.tmx)
            ("Shop", "new_map.tmx", 10, 8)
        ]
        self._navigate_buttons: list[Button] = []
        self._setup_navigate_buttons()
        self._navigate_close_button = Button(
            "UI/button_x.png", "UI/button_x_hover.png",
            0, 0, 48, 48,
            lambda: setattr(self, "navigate_active", False)
        )
        
        # Auto-navigation state
        self.is_navigating = False
        self.navigation_path: list[tuple[int, int]] = []
        self.current_nav_target: tuple[int, int] | None = None
        self.nav_teleport_pending: tuple[str, int, int] | None = None  # (target_map, target_x, target_y)
        # Track navigation intent across map changes
        self.nav_target_map: str | None = None
        self.nav_target_tile: tuple[int, int] | None = None
        self._nav_active_map: str = self.game_manager.current_map_key
        self.nav_speed = 120  # pixels per second

    def _setup_navigate_buttons(self):
        self._navigate_buttons.clear()
        # Buttons will be repositioned each frame in draw based on panel position.
        for name, map_key, tx, ty in self._navigate_locations:
            btn = Button(
                "UI/button_play.png", "UI/button_play_hover.png",
                0, 0, 80, 80,
                lambda mk=map_key, x=tx, y=ty: self._switch_to_map(mk, x, y)
            )
            self._navigate_buttons.append(btn)

    def _switch_to_map(self, map_key: str, target_x: int | None = None, target_y: int | None = None):
        """Navigate to target map and position by walking"""
        Logger.info(f"[Navigation] _switch_to_map called: target_map={map_key}, target=({target_x}, {target_y})")
        try:
            # Remember desired destination so we can replan after map changes
            self.nav_target_map = map_key
            self.nav_target_tile = (target_x, target_y) if target_x is not None and target_y is not None else None
            self._nav_active_map = self.game_manager.current_map_key

            # Normalize default target for shop
            if map_key == "new_map.tmx" and (target_x is None or target_y is None):
                target_x, target_y = 10, 8
                self.nav_target_tile = (target_x, target_y)
            
            # If target map is the same as current map, navigate directly
            if map_key == self.game_manager.current_map_key:
                Logger.info(f"[Navigation] Same map navigation")
                # Same map: directly start auto-navigation to target
                if target_x is not None and target_y is not None:
                    # Apply conditional routing based on current position and target
                    actual_target_x, actual_target_y = target_x, target_y
                    
                    if self.game_manager.player:
                        current_x = int(self.game_manager.player.position.x) // GameSettings.TILE_SIZE
                        current_y = int(self.game_manager.player.position.y) // GameSettings.TILE_SIZE
                        
                        # Gym navigation: if x <= 21, go right first to x > 21
                        if map_key == "gym.tmx" and current_x <= 21:
                            # First navigate to a point with x > 21 on current map, prioritizing RIGHT direction
                            Logger.info(f"[Navigation] Gym special routing: going right first")
                            self._start_auto_navigation(22, current_y, prefer_direction='RIGHT')
                            # After reaching that point, will continue to gym via _navigate_to_map
                            return
                        
                        # Start navigation: if x > 21, go down first to y >= 30, then left
                        if map_key == "map.tmx" and target_x == 16 and target_y == 30 and current_x > 21:
                            # First navigate down to y >= 30, prioritizing DOWN direction
                            Logger.info(f"[Navigation] Start special routing: going down first")
                            self._start_auto_navigation(current_x, 30, prefer_direction='DOWN')
                            # After reaching that, will continue to start point
                            return
                        
                        # Default: navigate directly to target
                        Logger.info(f"[Navigation] Direct navigation to ({actual_target_x}, {actual_target_y})")
                        self._start_auto_navigation(actual_target_x, actual_target_y)
                    else:
                        self._start_auto_navigation(actual_target_x, actual_target_y)
                else:
                    # No target means nothing to do
                    self.is_navigating = False
            else:
                # Different map: handle shop/gym chaining explicitly
                Logger.info(f"[Navigation] Different map navigation")
                current_map = self.game_manager.current_map_key

                # Gym from new_map: go back to map first, then proceed to gym
                if map_key == "gym.tmx" and current_map == "new_map.tmx":
                    Logger.info("[Navigation] Gym: from new_map -> map -> gym")
                    self._navigate_to_map("map.tmx", None, None)
                    return

                if map_key == "new_map.tmx":
                    if current_map == "map.tmx":
                        Logger.info("[Navigation] Shop: from map -> teleporter (16,27) -> shop")
                        self._navigate_to_map("new_map.tmx", target_x, target_y)
                    elif current_map == "gym.tmx":
                        Logger.info("[Navigation] Shop: from gym -> map -> teleporter (16,27) -> shop")
                        # First go back to map; subsequent logic will continue to shop
                        self._navigate_to_map("map.tmx", 16, 27)
                    else:
                        self._navigate_to_map(map_key, target_x, target_y)
                else:
                    # Generic different-map navigation
                    self._navigate_to_map(map_key, target_x, target_y)
        finally:
            self.navigate_active = False
    
    def _navigate_to_map(self, target_map: str, target_x: int | None = None, target_y: int | None = None):
        """Navigate to a different map by walking to teleporter then teleporting"""
        Logger.info(f"[Navigation] _navigate_to_map: current_map={self.game_manager.current_map_key}, target_map={target_map}, target=({target_x}, {target_y})")
        
        # Find the teleporter that leads to target_map (use first match only to avoid wrong routes)
        teleporters = self.game_manager.current_teleporter
        Logger.info(f"[Navigation] Available teleporters from {self.game_manager.current_map_key}: {len(teleporters)}")
        
        matching_teleporter = None
        for tp in teleporters:
            tp_x = int(tp.pos.x) // GameSettings.TILE_SIZE
            tp_y = int(tp.pos.y) // GameSettings.TILE_SIZE
            Logger.info(f"[Navigation]   Teleporter at ({tp_x}, {tp_y}) -> {tp.destination}")
            if tp.destination == target_map:
                matching_teleporter = tp
                Logger.info(f"[Navigation] ✓ Found matching teleporter to {target_map}!")
                break  # Use only the first matching teleporter to avoid unintended routes
        
        if matching_teleporter is None:
            Logger.error(f"[Navigation] ✗ No teleporter found from {self.game_manager.current_map_key} to {target_map}")
            self.is_navigating = False
            return
        
        # Navigate to the teleporter
        tp_tx = int(matching_teleporter.pos.x) // GameSettings.TILE_SIZE
        tp_ty = int(matching_teleporter.pos.y) // GameSettings.TILE_SIZE
        Logger.info(f"[Navigation] Starting navigation to teleporter at ({tp_tx}, {tp_ty})")
        
        # Store pending teleport info
        self.nav_teleport_pending = (target_map, target_x, target_y)
        
        # Start navigation to teleporter with fallback enabled; allow stepping onto teleporter even if collidable
        self._start_auto_navigation(tp_tx, tp_ty, allow_fallback=True, goal_is_teleporter=True)

    def _start_auto_navigation(self, target_tile_x: int, target_tile_y: int, prefer_direction: str | None = None, allow_fallback: bool = False, goal_is_teleporter: bool = False):
        """Start auto-navigation to target tile coordinates
        
        prefer_direction: None, 'RIGHT', 'LEFT', 'DOWN', or 'UP' - prioritize movement in this direction first
        allow_fallback: if True and direct path fails, try nearby tiles
        goal_is_teleporter: if True, allow stepping onto the destination tile even if marked collidable
        """
        if self.game_manager.player is None:
            return
        
        # Convert current position to tile coordinates
        start_tx = int(self.game_manager.player.position.x) // GameSettings.TILE_SIZE
        start_ty = int(self.game_manager.player.position.y) // GameSettings.TILE_SIZE
        
        # Simple pathfinding: use A* to find path
        path = self._find_path(start_tx, start_ty, target_tile_x, target_tile_y, prefer_direction, goal_is_teleporter)
        
        # If direct path fails and fallback is allowed, try finding a path to nearby accessible tiles
        if not path and allow_fallback:
            Logger.warning(f"[Navigation] Direct path to ({target_tile_x}, {target_tile_y}) failed, trying nearby tiles")
            # Try tiles around the target
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0:
                        continue
                    alt_x, alt_y = target_tile_x + dx, target_tile_y + dy
                    alt_path = self._find_path(start_tx, start_ty, alt_x, alt_y, prefer_direction)
                    if alt_path:
                        Logger.info(f"[Navigation] Found alternative path to ({alt_x}, {alt_y})")
                        path = alt_path
                        break
                if path:
                    break
        
        if path:
            self.navigation_path = path
            self.is_navigating = True
            self.current_nav_target = path[0] if path else None
            self._nav_active_map = self.game_manager.current_map_key
            Logger.info(f"[Navigation] Navigation started, path length: {len(path)}")
        else:
            Logger.warning(f"[Navigation] No path found to ({target_tile_x}, {target_tile_y}), navigation failed")
            self.is_navigating = False
    
    def _find_path(self, start_x: int, start_y: int, goal_x: int, goal_y: int, prefer_direction: str | None = None, goal_is_teleporter: bool = False) -> list[tuple[int, int]]:
        """A* pathfinding with preference for right-then-up movement and bush avoidance
        
        prefer_direction: prioritize movement in this direction first when costs are equal
        goal_is_teleporter: if True, allow the goal tile even if collidable/bush
        """
        from heapq import heappush, heappop
        
        def heuristic(x: int, y: int) -> int:
            # Manhattan distance
            return abs(x - goal_x) + abs(y - goal_y)
        
        def is_walkable(x: int, y: int) -> bool:
            if x < 0 or y < 0 or x >= self.game_manager.current_map.tmxdata.width or y >= self.game_manager.current_map.tmxdata.height:
                return False
            # If goal is a teleporter, allow stepping onto that tile even if collidable
            if not (goal_is_teleporter and x == goal_x and y == goal_y):
                # Check if tile is not colliding
                tile_rect = pg.Rect(x * GameSettings.TILE_SIZE, y * GameSettings.TILE_SIZE, GameSettings.TILE_SIZE, GameSettings.TILE_SIZE)
                if self.game_manager.current_map.check_collision(tile_rect):
                    return False
                # COMPLETELY block bushes - treat them as unwalkable for navigation
                try:
                    pos = Position(x * GameSettings.TILE_SIZE + GameSettings.TILE_SIZE // 2, 
                                 y * GameSettings.TILE_SIZE + GameSettings.TILE_SIZE // 2)
                    if self.game_manager.current_map.is_pokemon_bush_at(pos):
                        return False  # Block bushes entirely during navigation
                except Exception:
                    pass
            return True
        
        open_set = []
        heappush(open_set, (0, start_x, start_y))
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        g_score: dict[tuple[int, int], int] = {(start_x, start_y): 0}
        
        visited = set()
        
        while open_set:
            _, x, y = heappop(open_set)
            
            if (x, y) in visited:
                continue
            visited.add((x, y))
            
            if x == goal_x and y == goal_y:
                # Reconstruct path
                path = []
                current = (goal_x, goal_y)
                while current in came_from:
                    path.append(current)
                    current = came_from[current]
                path.append((start_x, start_y))
                return list(reversed(path))[1:]  # Exclude start, include goal
            
            # Check all 4 directions
            # Prefer direction determines priority: prefer_direction first, then other directions
            if prefer_direction == 'RIGHT':
                directions = [(1, 0), (0, 1), (0, -1), (-1, 0)]  # Right, Down, Up, Left
            elif prefer_direction == 'LEFT':
                directions = [(-1, 0), (0, 1), (0, -1), (1, 0)]  # Left, Down, Up, Right
            elif prefer_direction == 'DOWN':
                directions = [(0, 1), (1, 0), (-1, 0), (0, -1)]  # Down, Right, Left, Up
            elif prefer_direction == 'UP':
                directions = [(0, -1), (1, 0), (-1, 0), (0, 1)]  # Up, Right, Left, Down
            else:
                # Default: prefer right then down
                directions = [(1, 0), (0, 1), (0, -1), (-1, 0)]  # Right, Down, Up, Left
            
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                if not is_walkable(nx, ny) or (nx, ny) in visited:
                    continue
                
                # Simple cost = 1 (bushes already blocked in is_walkable)
                tentative_g = g_score[(x, y)] + 1
                
                if (nx, ny) not in g_score or tentative_g < g_score[(nx, ny)]:
                    came_from[(nx, ny)] = (x, y)
                    g_score[(nx, ny)] = tentative_g
                    f_score = tentative_g + heuristic(nx, ny)
                    heappush(open_set, (f_score, nx, ny))
        
        return []  # No path found

    def _replan_navigation_for_current_map(self):
        """Recalculate path when the current map changes while navigating."""
        self._nav_active_map = self.game_manager.current_map_key
        if not self.is_navigating:
            return
        if not self.nav_target_map:
            self.is_navigating = False
            return
        # If we are already on the destination map, go straight to the target tile.
        if self.game_manager.current_map_key == self.nav_target_map:
            if self.nav_target_tile:
                tx, ty = self.nav_target_tile
                self._start_auto_navigation(tx, ty)
            else:
                self.is_navigating = False
            return
        # Otherwise find a teleporter on this map that reaches the destination map.
        teleporters = self.game_manager.current_teleporter
        target_tp = None
        for tp in teleporters:
            if tp.destination == self.nav_target_map:
                target_tp = tp
                break
        if target_tp is None:
            Logger.warning(f"No teleporter found from {self.game_manager.current_map_key} to {self.nav_target_map}")
            self.is_navigating = False
            return
        self.nav_teleport_pending = (
            self.nav_target_map,
            self.nav_target_tile[0] if self.nav_target_tile else None,
            self.nav_target_tile[1] if self.nav_target_tile else None,
        )
        tp_tx = int(target_tp.pos.x) // GameSettings.TILE_SIZE
        tp_ty = int(target_tp.pos.y) // GameSettings.TILE_SIZE
        self._start_auto_navigation(tp_tx, tp_ty, goal_is_teleporter=True)

    def _update_auto_navigation(self, dt: float):
        """Update auto-navigation movement"""
        if not self.game_manager.player:
            self.is_navigating = False
            return
        
        # Check if we have a pending teleport to process (map switch completed)
        if self.nav_teleport_pending and not self.navigation_path:
            target_map, target_x, target_y = self.nav_teleport_pending
            self.nav_teleport_pending = None
            
            # Teleport to new map
            self.game_manager.switch_map(target_map, target_x, target_y)
            # Process the map switch
            self.game_manager.try_switch_map()
            self._nav_active_map = self.game_manager.current_map_key
            
            # Recalculate path on new map from current position to target
            if target_x is not None and target_y is not None:
                self._start_auto_navigation(target_x, target_y)
            else:
                self.is_navigating = False
            return
        
        # Check if no path left - navigation complete or need to continue with next stage
        if not self.navigation_path:
            # Check if we need to continue with conditional routing
            if self.nav_target_map and self.nav_target_tile:
                current_x = int(self.game_manager.player.position.x) // GameSettings.TILE_SIZE
                current_y = int(self.game_manager.player.position.y) // GameSettings.TILE_SIZE
                target_x, target_y = self.nav_target_tile

                # Shop routing chain
                if self.nav_target_map == "new_map.tmx":
                    # From gym: return to map first
                    if self.game_manager.current_map_key == "gym.tmx":
                        self._navigate_to_map("map.tmx", 16, 27)
                        return
                    # From map: go to teleporter that leads to shop
                    if self.game_manager.current_map_key == "map.tmx":
                        self._navigate_to_map("new_map.tmx", target_x, target_y)
                        return
                
                # Gym routing: after reaching x > 21, continue to gym
                if self.nav_target_map == "gym.tmx" and current_x > 21 and (current_x != target_x or current_y != target_y):
                    if self.game_manager.current_map_key == "map.tmx":
                        self._navigate_to_map("gym.tmx", target_x, target_y)
                        return
                
                # Start routing: after reaching y >= 30, continue to final position
                if self.nav_target_map == "map.tmx" and target_x == 16 and target_y == 30:
                    if current_y >= 30 and current_x > 21 and (current_x != target_x or current_y != target_y):
                        # Now navigate left to the final position
                        self._start_auto_navigation(target_x, target_y, prefer_direction='LEFT')
                        return
            
            self.is_navigating = False

            self.is_navigating = False
            return
        
        # Get current tile position
        current_tx = int(self.game_manager.player.position.x) // GameSettings.TILE_SIZE
        current_ty = int(self.game_manager.player.position.y) // GameSettings.TILE_SIZE
        
        # Check if reached current target
        if self.current_nav_target and (current_tx, current_ty) == self.current_nav_target:
            # Move to next waypoint in path
            if self.navigation_path:
                self.navigation_path.pop(0)
                if self.navigation_path:
                    self.current_nav_target = self.navigation_path[0]
                else:
                    # Path completed
                    self.is_navigating = False
                    return
        
        # Move towards current target
        if self.current_nav_target:
            target_tx, target_ty = self.current_nav_target
            target_x = target_tx * GameSettings.TILE_SIZE + GameSettings.TILE_SIZE // 2
            target_y = target_ty * GameSettings.TILE_SIZE + GameSettings.TILE_SIZE // 2
            
            # Calculate direction
            dx = target_x - self.game_manager.player.position.x
            dy = target_y - self.game_manager.player.position.y
            distance = (dx**2 + dy**2)**0.5
            
            if distance > 2:  # Small threshold to avoid jitter
                # Set player input to move towards target
                import math
                angle = math.atan2(dy, dx)
                
                # Determine direction: up, down, left, right
                if abs(dx) > abs(dy):
                    if dx > 0:
                        from src.utils import Direction
                        self.game_manager.player.direction = Direction.RIGHT
                        # Ensure animation faces movement while navigating
                        self.game_manager.player.animation.switch("right")
                    else:
                        from src.utils import Direction
                        self.game_manager.player.direction = Direction.LEFT
                        self.game_manager.player.animation.switch("left")
                else:
                    if dy > 0:
                        from src.utils import Direction
                        self.game_manager.player.direction = Direction.DOWN
                        self.game_manager.player.animation.switch("down")
                    else:
                        from src.utils import Direction
                        self.game_manager.player.direction = Direction.UP
                        self.game_manager.player.animation.switch("up")
                
                # Move player
                move_distance = self.nav_speed * dt
                if distance <= move_distance:
                    self.game_manager.player.position.x = target_x
                    self.game_manager.player.position.y = target_y
                else:
                    self.game_manager.player.position.x += (dx / distance) * move_distance
                    self.game_manager.player.position.y += (dy / distance) * move_distance
                
                self.game_manager.player.is_moving = True
            else:
                self.current_nav_target = None
        else:
            self.is_navigating = False


    def _handle_close_overlay(self):
        if self.backpack_active:
            self.backpack_active = False
        if self.overlay_active:
            self.overlay_active = False
        if self.shop_active:
            self.shop_active = False
            self.shop_overlay.close()

    def _close_overlay(self):
        self.overlay_active = False
        # Settings overlay UI (checkbox, slider) 僅在 overlay_active 時初始化
        self.setting_checkbox = None
        self.setting_slider = None

    def _close_backpack(self):
        self.backpack_active = False

    def _overlay_save(self):
        try:
            # Save current game manager state to default save file
            self.game_manager.save("saves/game0.json")
            Logger.info("Game saved (overlay)")
        except Exception as e:
            Logger.warning(f"Failed to save game from overlay: {e}")

    def _overlay_load(self):
        try:
            manager = GameManager.load("saves/game0.json")
            if manager is None:
                Logger.warning("Primary save load failed; attempting backup 'saves/backup.json'...")
                try:
                    with open("saves/backup.json", "r", encoding="utf-8") as bf:
                        data = bf.read()
                    with open("saves/game0.json", "w", encoding="utf-8") as pf:
                        pf.write(data)
                    manager = GameManager.load("saves/game0.json")
                except Exception as be:
                    Logger.error(f"Failed to load backup save: {be}")
            if manager is None:
                Logger.error("Failed to load game from saves/game0.json or backup")
                return
            # Replace current game manager with loaded one
            self.game_manager = manager
            # Update backpack overlay to use the new game manager
            self.backpack_overlay = BackpackOverlay(self.game_manager)
            # Close overlay after successful load
            self.overlay_active = False
            Logger.info("Game loaded (overlay)")
        except Exception as e:
            Logger.warning(f"Failed to load game from overlay: {e}")

    def _overlay_back(self):
        # Close the settings overlay and return to game
        self.overlay_active = False
        
        
    @override
    def enter(self) -> None:
        sound_manager.play_bgm("RBY 103 Pallet Town.ogg")
        if self.online_manager:
            self.online_manager.enter()
        
    @override
    def exit(self) -> None:
        if self.online_manager:
            self.online_manager.exit()
    
    def handle_event(self, event: pg.event.Event):
        """Handle pygame events"""
        # Chat input capture (before other overlays)
        if event.type == pg.KEYDOWN:
            if self.chat_active:
                if event.key == pg.K_RETURN:
                    if self.online_manager:
                        self.online_manager.send_chat(self.chat_text)
                    self.chat_text = ""
                    self.chat_active = False
                elif event.key == pg.K_ESCAPE:
                    self.chat_text = ""
                    self.chat_active = False
                elif event.key == pg.K_BACKSPACE:
                    self.chat_text = self.chat_text[:-1]
                else:
                    ch = getattr(event, "unicode", "")
                    if ch and 32 <= ord(ch) <= 126 and len(self.chat_text) < 120:
                        self.chat_text += ch
                return
            elif event.key == pg.K_t:
                self.chat_active = True
                self.chat_text = ""
                return
        # Shop overlay has priority
        if self.shop_active:
            self.shop_overlay.handle_event(event)
            # Check if shop was closed
            if not self.shop_overlay.active:
                self.shop_active = False
            return
        
        # Backpack overlay events
        if self.backpack_active:
            try:
                self.backpack_overlay.handle_event(event)
            except Exception:
                pass
            return
        
        # Settings overlay events
        if self.overlay_active:
            if self.setting_checkbox:
                self.setting_checkbox.handle_event(event)
            if self.setting_slider:
                self.setting_slider.handle_event(event)
            return
        # No explicit per-event handling for navigate overlay; buttons use input_manager in update
        
    @override
    def update(self, dt: float):
        self._last_dt = dt
        # Check if there is assigned next scene
        self.game_manager.try_switch_map()
        # If map changed externally (e.g., teleporter), replan navigation
        if self.is_navigating and self.game_manager.current_map_key != self._nav_active_map:
            self._replan_navigation_for_current_map()
        
        # Lock controls while chatting or during auto-navigation to prevent WASD movement
        if self.game_manager and self.game_manager.player:
            self.game_manager.controls_locked = bool(self.chat_active or self.is_navigating)
        
        # Handle auto-navigation
        if self.is_navigating and self.game_manager.player:
            self._update_auto_navigation(dt)
        
        # Check shop NPC interaction
        if not self.shop_active and not self.backpack_active and not self.overlay_active and not self.is_navigating:
            for shop_npc in self.game_manager.current_shop_npcs:
                shop_npc.update(dt)
                # Check if player pressed space near shop NPC
                if shop_npc.is_player_nearby:
                    from src.core.services import input_manager
                    if input_manager.key_pressed(pg.K_SPACE):
                        self.shop_active = True
                        self.shop_overlay.open()
                        break
        
        # Update shop overlay
        if self.shop_active:
            self.shop_overlay.update(dt)
        
        # Update player and other data
        if self.game_manager.player:
            self.game_manager.player.update(dt)
        # Update backpack button regardless of overlay state
        self.backpack_button.update(dt)
        # Update settings button as well
        self.settings_button.update(dt)
        # Update navigate button
        self.navigate_button.update(dt)
        if self.backpack_active:
            self.overlay_back_button.update(dt)
        # Update settings overlay
        if self.overlay_active:
            if self.setting_checkbox is None or self.setting_slider is None:
                from src.scenes.setting_scene import Checkbox, Slider
                px = GameSettings.SCREEN_WIDTH // 2
                py = GameSettings.SCREEN_HEIGHT // 2
                # initialize checkbox from GameSettings.MUTED
                self.setting_checkbox = Checkbox(px-100, py-100, "Mute Off", GameSettings.MUTED)
                # initialize slider from current GameSettings audio volume
                self.setting_slider = Slider(px-100, py-40, 200, 0, 100, GameSettings.AUDIO_VOLUME * 100)
            self.overlay_back_button.update(dt)
            self.overlay_save_button.update(dt)
            self.overlay_load_button.update(dt)
            self.overlay_close_button.update(dt)
            self.setting_checkbox.update(dt)
            self.setting_slider.update(dt)
        else:
            self.setting_checkbox = None
            self.setting_slider = None
        # Update navigate overlay buttons
        if self.navigate_active:
            for b in self._navigate_buttons:
                b.update(dt)
            self._navigate_close_button.update(dt)
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.update(dt)
            
        # Update others
        self.game_manager.bag.update(dt)

        # forward mouse wheel input to backpack overlay when active
        if self.backpack_active:
            try:
                from src.core.services import input_manager
                if getattr(input_manager, "mouse_wheel", 0) != 0:
                    # craft a lightweight MOUSEWHEEL-like event for the overlay
                    ev = pg.event.Event(pg.MOUSEWHEEL, {"y": getattr(input_manager, "mouse_wheel", 0)})
                    try:
                        self.backpack_overlay.handle_event(ev)
                    except Exception:
                        # fallback: directly adjust scroll_offset
                        self.backpack_overlay.scroll_offset -= getattr(input_manager, "mouse_wheel", 0) * self.backpack_overlay.scroll_speed
                        if self.backpack_overlay.scroll_offset < 0:
                            self.backpack_overlay.scroll_offset = 0
            except Exception:
                pass
            try:
                self.backpack_overlay.update(dt)
            except Exception:
                pass
        
        if self.game_manager.player is not None and self.online_manager is not None:
            _ = self.online_manager.update(
                self.game_manager.player.position.x, 
                self.game_manager.player.position.y,
                self.game_manager.current_map.path_name,
                direction=self.game_manager.player.direction.name,
                moving=self.game_manager.player.is_moving
            )
            try:
                self.chat_messages = self.online_manager.get_recent_chat(limit=6)
            except Exception:
                pass
        
    @override
    def draw(self, screen: pg.Surface):        
        if self.game_manager.player:
            '''
            [TODO HACKATHON 3]
            Implement the camera algorithm logic here
            Right now it's hard coded, you need to follow the player's positions
            you may use the below example, but the function still incorrect, you may trace the entity.py
            
            camera = self.game_manager.player.camera
            '''
            # Follow the player: use player's camera (centered & clamped)
            camera = self.game_manager.player.camera
            self.game_manager.current_map.draw(screen, camera)
            self.game_manager.player.draw(screen, camera)
        else:
            camera = PositionCamera(0, 0)
            self.game_manager.current_map.draw(screen, camera)
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.draw(screen, camera)
        
        # Draw shop NPCs
        for shop_npc in self.game_manager.current_shop_npcs:
            shop_npc.draw(screen, camera)

        self.game_manager.bag.draw(screen)
        
        if self.online_manager and self.game_manager.player:
            list_online = self.online_manager.get_list_players()
            seen_ids: set[int] = set()
            for player in list_online:
                if player["map"] == self.game_manager.current_map.path_name:
                    cam = self.game_manager.player.camera
                    pos = cam.transform_position_as_position(Position(player["x"], player["y"]))
                    pid = player.get("id")
                    seen_ids.add(pid)
                    anim = self.online_sprites.get(pid)
                    if anim is None:
                        anim = Animation(
                            "character/ow1.png", ["down", "left", "right", "up"], 4,
                            (GameSettings.TILE_SIZE, GameSettings.TILE_SIZE)
                        )
                        self.online_sprites[pid] = anim
                    dir_name = str(player.get("direction", "DOWN")).lower()
                    if dir_name == "left":
                        anim.switch("left")
                    elif dir_name == "right":
                        anim.switch("right")
                    elif dir_name == "up":
                        anim.switch("up")
                    else:
                        anim.switch("down")
                    if player.get("moving", False):
                        anim.update(self._last_dt)
                    anim.update_pos(pos)
                    anim.draw(screen)
            # Cleanup sprites for players who left
            stale_ids = [pid for pid in self.online_sprites.keys() if pid not in seen_ids]
            for sid in stale_ids:
                del self.online_sprites[sid]
        
        # Draw minimap
        self._draw_minimap(screen)
        
        # Draw settings button then backpack button
        self.settings_button.draw(screen)
        self.navigate_button.draw(screen)
        self.backpack_button.draw(screen)

        # Settings overlay
        if self.overlay_active:
            # 背景變暗
            dark = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
            dark.fill((0,0,0,128))
            screen.blit(dark, (0,0))
            # overlay 視窗與背包一致
            from src.core.services import resource_manager
            bg_img = resource_manager.get_image("UI/raw/UI_Flat_Frame03a.png")
            bg_img = pg.transform.scale(bg_img, (700, 500))
            panel_w, panel_h = 700, 500
            panel_x = GameSettings.SCREEN_WIDTH // 2 - panel_w // 2
            panel_y = GameSettings.SCREEN_HEIGHT // 2 - panel_h // 2
            screen.blit(bg_img, (panel_x, panel_y))
            # Back button
            self.overlay_back_button.hitbox.topleft = (panel_x + panel_w - 48 - 10, panel_y + 10)
            self.overlay_back_button.draw(screen)
            # Checkbox 與 Slider，M與V左側對齊
            align_x = panel_x + 60
            cb_y = panel_y + 150
            self.setting_checkbox.rect.topleft = (align_x, cb_y)
            self.setting_checkbox.align_x = align_x
            self.setting_checkbox.draw(screen)
            sl_y = cb_y + 80
            self.setting_slider.rect.topleft = (align_x + 90, sl_y)
            self.setting_slider.align_x = align_x
            self.setting_slider.draw(screen)
            # Save / Load / Back buttons at bottom of panel (each square: height == width)
            spacing = 24
            w1 = self.overlay_save_button.hitbox.w
            w2 = self.overlay_load_button.hitbox.w
            w3 = self.overlay_close_button.hitbox.w
            total_w = w1 + w2 + w3 + spacing * 2
            start_x = panel_x + panel_w // 2 - total_w // 2
            # vertically center buttons at bottom with a margin
            btn_y = panel_y + panel_h - max(w1, w2, w3) - 30

            self.overlay_save_button.hitbox.topleft = (start_x, btn_y)
            self.overlay_load_button.hitbox.topleft = (start_x + w1 + spacing, btn_y)
            self.overlay_close_button.hitbox.topleft = (start_x + w1 + spacing + w2 + spacing, btn_y)

            self.overlay_save_button.draw(screen)
            self.overlay_load_button.draw(screen)
            self.overlay_close_button.draw(screen)

        # Backpack overlay
        if self.backpack_active:
            # Draw custom background for backpack overlay
            from src.core.services import resource_manager
            bg_img = resource_manager.get_image("UI/raw/UI_Flat_Frame03a.png")
            bg_img = pg.transform.scale(bg_img, (700, 500))
            panel_w, panel_h = 700, 500
            panel_x = GameSettings.SCREEN_WIDTH // 2 - panel_w // 2
            panel_y = GameSettings.SCREEN_HEIGHT // 2 - panel_h // 2
            screen.blit(bg_img, (panel_x, panel_y))

            # Position overlay back button at top-right of panel
            self.overlay_back_button.hitbox.topleft = (panel_x + panel_w - 48 - 10, panel_y + 10)
            self.overlay_back_button.draw(screen)

            # Use BackpackOverlay to draw content (handles scrolling internally)
            try:
                self.backpack_overlay.draw_content(screen, panel_x, panel_y, panel_w, panel_h)
            except Exception:
                # fallback: no-op
                pass
        
        # Shop overlay (draw on top of everything)
        if self.shop_active:
            self.shop_overlay.draw(screen)

        # Chat overlay (simple bottom-left panel) draws below navigate overlay
        chat_drawn = False
        if self.online_manager:
            box_w = 420
            box_h = 140
            panel = pg.Surface((box_w, box_h), pg.SRCALPHA)
            panel.fill((0, 0, 0, 140))
            screen.blit(panel, (10, GameSettings.SCREEN_HEIGHT - box_h - 10))

            # Recent messages
            y = GameSettings.SCREEN_HEIGHT - box_h + 5
            for msg in self.chat_messages[-5:]:
                sender_id = msg.get("from", "?")
                # Map real player ID to stable display ID
                if isinstance(sender_id, int):
                    if sender_id not in self._player_id_map:
                        self._player_id_map[sender_id] = self._next_display_id
                        self._next_display_id += 1
                    sender = self._player_id_map[sender_id]
                else:
                    sender = sender_id
                text = msg.get("text", "")
                line = f"{sender}: {text}"
                surf = self.chat_font.render(line, True, (255, 255, 255))
                screen.blit(surf, (20, y))
                y += 22

            # Input line
            input_prefix = "> " if self.chat_active else "press T to chat"
            input_text = f"{input_prefix}{self.chat_text if self.chat_active else ''}"
            surf = self.chat_font.render(input_text, True, (200, 220, 255))
            screen.blit(surf, (20, GameSettings.SCREEN_HEIGHT - 35))
            chat_drawn = True

        # Navigate overlay (draw on very top)
        if self.navigate_active:
            # dark background
            dark = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
            dark.fill((0,0,0,128))
            screen.blit(dark, (0,0))
            # panel background image consistent with other overlays
            from src.core.services import resource_manager
            bg_img = resource_manager.get_image("UI/raw/UI_Flat_Frame03a.png")
            panel_w, panel_h = 700, 400
            bg_img = pg.transform.scale(bg_img, (panel_w, panel_h))
            panel_x = GameSettings.SCREEN_WIDTH // 2 - panel_w // 2
            panel_y = GameSettings.SCREEN_HEIGHT // 2 - panel_h // 2
            screen.blit(bg_img, (panel_x, panel_y))
            # title
            font_title = pg.font.SysFont("arial", 28, bold=True)
            title = font_title.render("Navigate To", True, (20,20,20))
            screen.blit(title, (panel_x + panel_w//2 - title.get_width()//2, panel_y + 20))
            # position buttons in panel center
            button_spacing = 160
            total_w = len(self._navigate_buttons) * 80 + (len(self._navigate_buttons) - 1) * (button_spacing - 80)
            start_x = panel_x + panel_w // 2 - total_w // 2
            btn_y = panel_y + panel_h // 2 - 40
            for i, btn in enumerate(self._navigate_buttons):
                btn.hitbox.topleft = (start_x + i * button_spacing, btn_y)
                btn.draw(screen)
                # labels under buttons
                name = self._navigate_locations[i][0]
                font_label = pg.font.SysFont("arial", 18)
                label = font_label.render(name, True, (20,20,20))
                lr = label.get_rect(center=(btn.hitbox.centerx, btn.hitbox.bottom + 18))
                screen.blit(label, lr)
            # close button at top-right of panel
            self._navigate_close_button.hitbox.topleft = (panel_x + panel_w - 48 - 10, panel_y + 10)
            self._navigate_close_button.draw(screen)
    
    def _draw_minimap(self, screen: pg.Surface):
        """Draw a minimap in the top-left corner showing the current map and player position"""
        if not self.game_manager or not self.game_manager.current_map:
            return
        
        # Get map dimensions
        map_width = self.game_manager.current_map.tmxdata.width
        map_height = self.game_manager.current_map.tmxdata.height
        
        # Calculate aspect ratio and size to fit in available space
        max_size = 150
        aspect_ratio = map_width / map_height
        
        if aspect_ratio >= 1:
            # Wider map
            minimap_width = max_size
            minimap_height = int(max_size / aspect_ratio)
        else:
            # Taller map
            minimap_height = max_size
            minimap_width = int(max_size * aspect_ratio)
        
        # Calculate scale for minimap
        scale_x = minimap_width / (map_width * GameSettings.TILE_SIZE)
        scale_y = minimap_height / (map_height * GameSettings.TILE_SIZE)
        
        # Create minimap surface by scaling the original map
        try:
            # Create a scaled version of the map surface
            minimap_surface = pg.transform.scale(
                self.game_manager.current_map._surface,
                (minimap_width, minimap_height)
            )
        except Exception:
            # Fallback if scaling fails
            minimap_surface = pg.Surface((minimap_width, minimap_height))
            minimap_surface.fill((100, 150, 100))
        
        # Draw minimap background border
        minimap_bg = pg.Surface((minimap_width + 4, minimap_height + 4))
        minimap_bg.fill((100, 100, 100))  # Dark gray background
        screen.blit(minimap_bg, (self.minimap_x - 2, self.minimap_y - 2))
        
        # Draw the minimap
        screen.blit(minimap_surface, (self.minimap_x, self.minimap_y))
        
        # Draw player position on minimap
        if self.game_manager.player:
            player_x = self.game_manager.player.position.x
            player_y = self.game_manager.player.position.y
            
            # Scale player position to minimap
            minimap_player_x = int(player_x * scale_x) + self.minimap_x
            minimap_player_y = int(player_y * scale_y) + self.minimap_y
            
            # Draw player as a small circle
            player_color = (0, 0, 255)  # Blue
            pg.draw.circle(screen, player_color, (minimap_player_x, minimap_player_y), 4)
            # Draw white outline for visibility
            pg.draw.circle(screen, (255, 255, 255), (minimap_player_x, minimap_player_y), 4, 1)
        
        # Draw border around minimap
        pg.draw.rect(screen, (0, 0, 0), (self.minimap_x - 2, self.minimap_y - 2, minimap_width + 4, minimap_height + 4), 2)
