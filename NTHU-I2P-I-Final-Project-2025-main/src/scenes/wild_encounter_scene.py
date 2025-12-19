import pygame as pg
import random
from src.scenes.scene import Scene
from src.core.services import scene_manager, resource_manager
from src.interface.components import Button
from src.utils import Logger, GameSettings

class WildEncounterScene(Scene):
    def __init__(self):
        super().__init__()
        self.wild = None
        self.catch_button = None
        self.font = pg.font.SysFont(None, 28)

    def enter(self) -> None:
        Logger.info("Entering WildEncounterScene")
        # Obtain GameManager from scene_manager (set by Player before switching)
        gm = getattr(scene_manager, "wild_source_gm", None)
        # Prepare candidate wild pokemon (simple list)
        candidates = [
            {"name": "Rattata", "hp": 50, "max_hp": 50, "level": 7, "sprite_path": "menu_sprites/menusprite7.png", "element": "Normal", "exp": 0, "exp_to_next_level": 80},
            {"name": "Pidgey", "hp": 95, "max_hp": 95, "level": 16, "sprite_path": "menu_sprites/menusprite8.png", "element": "Normal", "exp": 0, "exp_to_next_level": 289},
            {"name": "Zubat", "hp": 195, "max_hp": 195, "level": 36, "sprite_path": "menu_sprites/menusprite9.png", "element": "Grass", "exp": 0, "exp_to_next_level": 12960},
            {"name": "Caterpie", "hp": 50, "max_hp": 50, "level": 7, "sprite_path": "menu_sprites/menusprite10.png", "element": "Grass", "exp": 0, "exp_to_next_level": 80},
        ]
        self.wild = random.choice(candidates)
        # Create catch button
        bx = GameSettings.SCREEN_WIDTH // 2 - 80
        by = GameSettings.SCREEN_HEIGHT - 140
        self.catch_button = Button("UI/raw/UI_Flat_Button02a_1.png", "UI/raw/UI_Flat_Button02a_2.png", bx, by, 160, 44, on_click=self._catch)

    def _catch(self):
        gm = getattr(scene_manager, "wild_source_gm", None)
        if gm is None:
            Logger.warning("No GameManager available to add caught monster")
        else:
            # Append wild to bag
            try:
                gm.bag.add_monster(self.wild)
                Logger.info(f"Caught {self.wild.get('name')}, added to bag (in-memory)")
            except Exception as e:
                Logger.warning(f"Failed to add monster to bag: {e}")
        # return to game
        scene_manager.change_scene("game")

    def exit(self) -> None:
        # clear temporary holder
        if hasattr(scene_manager, "wild_source_gm"):
            try:
                delattr(scene_manager, "wild_source_gm")
            except Exception:
                pass

    def update(self, dt: float) -> None:
        # Buttons
        if self.catch_button:
            self.catch_button.update(dt)

    def draw(self, screen: pg.Surface) -> None:
        # Dim background
        dark = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
        dark.fill((0,0,0,180))
        screen.blit(dark, (0,0))
        # Draw a simple centered panel
        try:
            panel = resource_manager.get_image("UI/raw/UI_Flat_Frame03a.png")
            panel = pg.transform.scale(panel, (500, 300))
            px = GameSettings.SCREEN_WIDTH // 2 - 250
            py = GameSettings.SCREEN_HEIGHT // 2 - 150
            screen.blit(panel, (px, py))
        except Exception:
            px = GameSettings.SCREEN_WIDTH // 2 - 250
            py = GameSettings.SCREEN_HEIGHT // 2 - 150
            pg.draw.rect(screen, (240,240,240), (px, py, 500, 300))

        # Show wild pokemon name and level
        if self.wild:
            name = self.wild.get("name", "?")
            level = self.wild.get("level", 1)
            txt = self.font.render(f"A wild {name} appeared! Lv{level}", True, (0,0,0))
            screen.blit(txt, (px + 20, py + 20))
            # Show sprite if available
            sp = None
            try:
                sp = resource_manager.get_image(self.wild.get("sprite_path", ""))
            except Exception:
                sp = None
            if sp:
                ss = pg.transform.scale(sp, (120, 120))
                screen.blit(ss, (px + 20, py + 60))
            # HP bar
            hp = self.wild.get("hp", 0)
            maxhp = self.wild.get("max_hp", hp)
            hp_x = px + 160
            hp_y = py + 80
            hp_w = 220
            hp_h = 14
            pg.draw.rect(screen, (120,120,120), (hp_x, hp_y, hp_w, hp_h))
            fill = int(hp_w * (hp / max(1, maxhp))) if maxhp>0 else 0
            pg.draw.rect(screen, (40,200,40), (hp_x, hp_y, fill, hp_h))
            hp_txt = self.font.render(f"{hp}/{maxhp}", True, (0,0,0))
            screen.blit(hp_txt, (hp_x, hp_y + hp_h + 4))

        # Draw catch button
        if self.catch_button:
            try:
                self.catch_button.draw(screen)
            except Exception:
                pass
