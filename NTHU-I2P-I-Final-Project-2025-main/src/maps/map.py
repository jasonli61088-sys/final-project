import pygame as pg
import pytmx

from src.utils import load_tmx, Position, GameSettings, PositionCamera, Teleport

class Map:
    # Map Properties
    path_name: str
    tmxdata: pytmx.TiledMap
    # Position Argument
    spawn: Position
    teleporters: list[Teleport]
    # Rendering Properties
    _surface: pg.Surface
    _collision_map: list[pg.Rect]

    def __init__(self, path: str, tp: list[Teleport], spawn: Position):
        self.path_name = path
        self.tmxdata = load_tmx(path)
        self.spawn = spawn
        self.teleporters = tp

        pixel_w = self.tmxdata.width * GameSettings.TILE_SIZE
        pixel_h = self.tmxdata.height * GameSettings.TILE_SIZE

        # Prebake the map
        self._surface = pg.Surface((pixel_w, pixel_h), pg.SRCALPHA)
        self._render_all_layers(self._surface)
        # Prebake the collision map
        self._collision_map = self._create_collision_map()

    def update(self, dt: float):
        return

    def draw(self, screen: pg.Surface, camera: PositionCamera):
        screen.blit(self._surface, camera.transform_position(Position(0, 0)))
        
        # Draw the hitboxes collision map
        if GameSettings.DRAW_HITBOXES:
            ts = GameSettings.TILE_SIZE
            for rect in self._collision_map:
                if rect.w < ts or rect.h < ts:
                    dw = ts - rect.w
                    dh = ts - rect.h
                    display_rect = rect.inflate(dw, dh)
                else:
                    display_rect = rect
                pg.draw.rect(screen, (255, 0, 0), camera.transform_rect(display_rect), 1)
        
    def check_collision(self, rect: pg.Rect) -> bool:
        '''
        [TODO HACKATHON 4]
        Return True if collide if rect param collide with self._collision_map
        Hint: use API colliderect and iterate each rectangle to check
        '''
        for r in self._collision_map:
            if rect.colliderect(r):
                return True
        return False
        
    def check_teleport(self, pos: Position) -> Teleport | None:
        '''[TODO HACKATHON 6] 
        Teleportation: Player can enter a building by walking into certain tiles defined inside saves/*.json, and the map will be changed
        Hint: Maybe there is an way to switch the map using something from src/core/managers/game_manager.py called switch_... 
        '''
        # Convert player position to tile coordinates
        tx = int(pos.x) // GameSettings.TILE_SIZE
        ty = int(pos.y) // GameSettings.TILE_SIZE

        for tp in self.teleporters:
            ttx = int(tp.pos.x) // GameSettings.TILE_SIZE
            tty = int(tp.pos.y) // GameSettings.TILE_SIZE
            if tx == ttx and ty == tty:
                return tp
        return None

    def _render_all_layers(self, target: pg.Surface) -> None:
        for layer in self.tmxdata.visible_layers:
            if isinstance(layer, pytmx.TiledTileLayer):
                self._render_tile_layer(target, layer)
            # elif isinstance(layer, pytmx.TiledImageLayer) and layer.image:
            #     target.blit(layer.image, (layer.x or 0, layer.y or 0))
 
    def _render_tile_layer(self, target: pg.Surface, layer: pytmx.TiledTileLayer) -> None:
        for x, y, gid in layer:
            if gid == 0:
                continue
            image = self.tmxdata.get_tile_image_by_gid(gid)
            if image is None:
                continue

            image = pg.transform.scale(image, (GameSettings.TILE_SIZE, GameSettings.TILE_SIZE))
            target.blit(image, (x * GameSettings.TILE_SIZE, y * GameSettings.TILE_SIZE))
    
    def _create_collision_map(self) -> list[pg.Rect]:
        rects = []
        for layer in self.tmxdata.visible_layers:
            if isinstance(layer, pytmx.TiledTileLayer) and ("collision" in layer.name.lower() or "house" in layer.name.lower()):
                for x, y, gid in layer:
                    if gid != 0:
                        '''
                        [TODO HACKATHON 4]
                        rects.append(pg.Rect(...))
                        Append the collision rectangle to the rects[] array
                        Remember scale the rectangle with the TILE_SIZE from settings
                        '''
                        # shrink collision rect slightly so narrow passages and visual gaps are handled more forgivingly
                        ts = GameSettings.TILE_SIZE
                        r = pg.Rect(x * ts, y * ts, ts, ts)
                        # only apply a small inset when tile is reasonably large
                        if ts > 6:
                            # inset by 2 pixels (1px each side) to avoid one-pixel visual gaps causing hard collisions
                            r.inflate_ip(-2, -2)
                        rects.append(r)
        return rects

    def is_pokemon_bush_at(self, pos) -> bool:
        """Return True if the given world Position falls on a tile in the 'PokemonBush' layer."""
        try:
            tx = int(pos.x) // GameSettings.TILE_SIZE
            ty = int(pos.y) // GameSettings.TILE_SIZE
        except Exception:
            return False
        # Some TMX files may name the bush layer differently (e.g. 'Bush', 'PokemonBush').
        # Consider any layer whose name contains 'bush' (case-insensitive).
        # Also sample multiple points within the player's tile area to be robust against
        # differing player anchor points (top-left vs feet).
        ts = GameSettings.TILE_SIZE
        sample_offsets = [
            (0, 0),
            (ts - 1, 0),
            (0, ts - 1),
            (ts - 1, ts - 1),
            (ts // 2, ts // 2),
        ]
        sample_tiles = set()
        try:
            for ox, oy in sample_offsets:
                sx = int((pos.x + ox)) // ts
                sy = int((pos.y + oy)) // ts
                sample_tiles.add((sx, sy))
        except Exception:
            pass

        for layer in self.tmxdata.visible_layers:
            lname = getattr(layer, "name", "")
            if not lname:
                continue
            if "bush" not in lname.lower():
                continue
            # check any of the sampled tiles
            for x, y, gid in layer:
                if gid == 0:
                    continue
                if (x, y) in sample_tiles:
                    return True
        return False

    @classmethod
    def from_dict(cls, data: dict) -> "Map":
        tp = [Teleport.from_dict(t) for t in data["teleport"]]
        pos = Position(data["player"]["x"] * GameSettings.TILE_SIZE, data["player"]["y"] * GameSettings.TILE_SIZE)
        return cls(data["path"], tp, pos)

    def to_dict(self):
        return {
            "path": self.path_name,
            "teleport": [t.to_dict() for t in self.teleporters],
            "player": {
                "x": self.spawn.x // GameSettings.TILE_SIZE,
                "y": self.spawn.y // GameSettings.TILE_SIZE,
            }
        }
