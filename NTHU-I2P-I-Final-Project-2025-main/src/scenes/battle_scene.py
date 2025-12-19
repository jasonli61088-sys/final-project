import pygame as pg
import os
from src.scenes.scene import Scene
from src.core.services import scene_manager, sound_manager, resource_manager
from src.utils import Logger, GameSettings
from src.utils.definition import effectiveness_multiplier
from typing import override
from src.interface.components import Button
import re

class BattleScene(Scene):
    def __init__(self):
        super().__init__()
        # Minimal battle state; will be initialized in enter()
        self.player_hp = 100
        self.player_max = 100
        self.enemy_hp = 50
        self.enemy_max = 50
        self.turn = "player"  # 'player' or 'enemy'
        self.font = pg.font.SysFont(None, 28)
        # UI assets (loaded in init so we can reuse)
        try:
            self.bg_img = resource_manager.get_image("backgrounds/background1.png")
        except Exception:
            self.bg_img = None
        try:
            self.ui_frame = resource_manager.get_image("UI/raw/UI_Flat_Frame03a.png")
        except Exception:
            self.ui_frame = None
        # button image (use a flat button asset)
        try:
            self.button_img = resource_manager.get_image("UI/raw/UI_Flat_Button02a_1.png")
        except Exception:
            self.button_img = None
        # banner image to place behind sprites
        try:
            self.banner_img = resource_manager.get_image("UI/raw/UI_Flat_Banner03a.png")
        except Exception:
            self.banner_img = None
        # small name frame for labels
        try:
            self.name_frame = resource_manager.get_image("UI/raw/UI_Flat_Frame01a.png")
        except Exception:
            self.name_frame = None

        # Buttons area (four actions)
        btn_w, btn_h = 160, 44
        gap = 20
        total_w = btn_w * 4 + gap * 3
        start_x = (GameSettings.SCREEN_WIDTH - total_w) // 2
        # move buttons slightly lower so they don't overlap the info text
        y = GameSettings.SCREEN_HEIGHT - 80
        self.button_rects = [pg.Rect(start_x + i * (btn_w + gap), y, btn_w, btn_h) for i in range(4)]
        # create Button components with hover/pressed effects
        self.action_buttons: list[Button] = []
        btn_paths = [
            ("UI/raw/UI_Flat_Button02a_1.png", "UI/raw/UI_Flat_Button02a_2.png"),
            ("UI/raw/UI_Flat_Button02a_1.png", "UI/raw/UI_Flat_Button02a_2.png"),
            ("UI/raw/UI_Flat_Button02a_1.png", "UI/raw/UI_Flat_Button02a_2.png"),
            ("UI/raw/UI_Flat_Button02a_1.png", "UI/raw/UI_Flat_Button02a_2.png"),
        ]
        for i, rect in enumerate(self.button_rects):
            default_path, hover_path = btn_paths[i]
            # on_click handlers will be bound later in enter()
            btn = Button(default_path, hover_path, rect.x, rect.y, rect.w, rect.h, on_click=None)
            self.action_buttons.append(btn)
        self.info = ""
        # thumbnails (small icons next to names)
        self.player_thumb = None
        self.enemy_thumb = None
        # small delay so player messages are visible before enemy action
        # message sequencing state:
        # message_phase: 0 idle, 2 enemy follow-up pending after player's immediate action
        self.message_timer = 0.0
        self.message_phase = 0
        self.pending_player_damage = 0
        self.pending_player_msg = ""
        self.pending_enemy_attack = False
        
        # Attack values (will be loaded from Pokemon data)
        self.player_attack = 12
        self.enemy_attack = 8
        
        # Pokemon overlay state
        self.show_overlay = False
        self.overlay_scroll = 0
        self.overlay_max_scroll = 0
        self.switch_buttons = []  # List of (rect, pokemon_index) tuples
        self.current_pokemon_index = 0  # Index of currently active Pokemon
        
        # Items overlay state
        self.show_items_overlay = False
        self.items_overlay_scroll = 0
        self.items_overlay_max_scroll = 0
        self.item_buttons = []  # List of (rect, item_index) tuples
        
        # Battle modifiers
        self.player_attack_multiplier = 1.0  # Strength Potion effect
        self.enemy_attack_multiplier = 1.0  # Defense Potion effect

    @override
    def enter(self) -> None:
        Logger.info("Entering battle scene")
        # Reset to first Pokemon at the start of each battle
        self.current_pokemon_index = 0
        # initialize element defaults
        self.player_element = "Normal"
        self.enemy_element = "Normal"
        # initialize battle state from scene_manager.battle_target if present
        target = getattr(scene_manager, "battle_target", None)
        gm = None
        try:
            # try to get the game manager from the target
            if target is not None:
                gm = target.game_manager
                # store simple HP values
                # If original entities have hp, attempt to read; otherwise use defaults
                self.enemy_hp = getattr(target, "hp", 50)
                self.enemy_max = getattr(target, "max_hp", self.enemy_hp)
                if gm and gm.player is not None:
                    self.player_hp = getattr(gm.player, "hp", 100)
                    self.player_max = getattr(gm.player, "max_hp", self.player_hp)
        except Exception:
            pass
        # Default to player turn first and prompt
        self.turn = "player"
        self.info = "What will Player do?"
        # reset message sequencing
        self.message_timer = 0.0
        self.message_phase = 0
        self.pending_player_damage = 0
        self.pending_player_msg = ""
        self.pending_enemy_attack = False
        Logger.info(f"Battle initialized: player_hp={self.player_hp}, enemy_hp={self.enemy_hp}")
        # attempt to load player/enemy sprites if specified on battle_target
        self.player_sprite = None
        self.enemy_sprite = None
        # basic stat placeholders
        self.enemy_name = "Enemy"
        self.enemy_level = 1
        self.enemy_hp = self.enemy_hp
        self.enemy_max = self.enemy_max

        self.player_name = "Player"
        self.player_level = 1
        self.player_hp = self.player_hp
        self.player_max = self.player_max
        target = getattr(scene_manager, "battle_target", None)
        try:
            if target is not None:
                # trainers may have a 'sprite_path' attribute
                sprite_path = getattr(target, "sprite_path", None)
                def try_variants(base_path, suffixes):
                    if not base_path:
                        return None
                    name, ext = os.path.splitext(base_path)
                    for s in suffixes:
                        candidate = f"{name}{s}{ext}"
                        try:
                            return resource_manager.get_image(candidate)
                        except Exception:
                            continue
                    # try base last
                    try:
                        return resource_manager.get_image(base_path)
                    except Exception:
                        return None

                def try_with_keyword(base_path, keyword, suffixes):
                    """Try candidate filenames that include a keyword (e.g. '_pokemon' or '_enemy') before other fallbacks."""
                    if not base_path:
                        return None
                    name, ext = os.path.splitext(base_path)
                    # try keyword variants first
                    candidates = [f"{name}{keyword}{ext}"] + [f"{name}{keyword}{s}{ext}" for s in suffixes]
                    for c in candidates:
                        try:
                            return resource_manager.get_image(c)
                        except Exception:
                            continue
                    # if none found, fall back to normal try_variants
                    return try_variants(base_path, suffixes)

                def element_from_sprite_path(path: str | None) -> str:
                    """Map specific sprite filenames to elements: Grass, Fire, Water; default Normal."""
                    if not path:
                        return "Normal"
                    try:
                        fname = os.path.basename(path)
                        m = re.search(r"(sprite)(\d+)", fname)
                        idx = int(m.group(2)) if m else None
                    except Exception:
                        idx = None
                    # mapping per request
                    grass = {1, 2, 3, 15, 16}
                    fire = {4, 5, 7, 8, 9}
                    water = {6, 10, 11, 12, 13, 14}
                    if idx in grass:
                        return "Grass"
                    if idx in fire:
                        return "Fire"
                    if idx in water:
                        return "Water"
                    return "Normal"

                def select_side_from_image(surf: pg.Surface, side: str) -> pg.Surface:
                    """
                    If an image contains two side-by-side characters, split and return the requested side.
                    side: 'player' -> right half, 'enemy' -> left half.
                    If the image is not wide enough, return surf unchanged.
                    """
                    if surf is None:
                        return None
                    w, h = surf.get_width(), surf.get_height()
                    # If width is at least 2x height, assume two side-by-side sprites
                    if w >= 2 * h:
                        half_w = w // 2
                        if side == "player":
                            rect = pg.Rect(half_w, 0, half_w, h)
                        else:
                            rect = pg.Rect(0, 0, half_w, h)
                        try:
                            return surf.subsurface(rect).copy()
                        except Exception:
                            return surf
                    # Also allow splitting if width >= 2 * some expected sprite width (220)
                    if w >= 440:
                        half_w = w // 2
                        if side == "player":
                            rect = pg.Rect(half_w, 0, half_w, h)
                        else:
                            rect = pg.Rect(0, 0, half_w, h)
                        try:
                            return surf.subsurface(rect).copy()
                        except Exception:
                            return surf
                    return surf

                if sprite_path:
                    # prefer filenames that include '_enemy' for enemy-side sprites
                    loaded = try_with_keyword(sprite_path, "_enemy", ["_front", "_left", "_attack", "_idle"])
                    # select left half for enemy if image contains two sprites
                    self.enemy_sprite = select_side_from_image(loaded, "enemy")
                    self.enemy_element = element_from_sprite_path(sprite_path)
                # detailed stats from trainer
                self.enemy_name = getattr(target, "name", getattr(target, "trainer_name", self.enemy_name))
                self.enemy_level = getattr(target, "level", getattr(target, "lvl", self.enemy_level))
                self.enemy_hp = getattr(target, "hp", self.enemy_hp)
                self.enemy_max = getattr(target, "max_hp", getattr(target, "maxhp", self.enemy_max))
                self.enemy_attack = getattr(target, "attack", 8)
                # try to get player sprite from game manager if available
                gm = getattr(target, "game_manager", None)
                if gm and getattr(gm, "player", None) is not None:
                    p = gm.player
                    ps = getattr(p, "sprite_path", None)
                    if ps:
                        # player prefers back/right variants
                        # prefer filenames that include '_pokemon' for player-side sprites
                        loaded_p = try_with_keyword(ps, "_pokemon", ["_back", "_right", "_idle", "_attack"])
                        # select right half for player if image contains two sprites
                        self.player_sprite = select_side_from_image(loaded_p, "player")
                        self.player_element = element_from_sprite_path(ps)
                    # fallback defaults if still missing
                    if not self.player_sprite:
                        loaded_def = try_with_keyword("sprites/sprite1.png", "_pokemon", ["_back", "_right", "_idle"])
                        self.player_sprite = select_side_from_image(loaded_def, "player")
                        self.player_element = element_from_sprite_path("sprites/sprite1.png")
                # if enemy sprite missing, pick a default from sprites
                if not self.enemy_sprite:
                    loaded_def_e = try_with_keyword("sprites/sprite10.png", "_enemy", ["_front", "_left", "_idle"]) 
                    self.enemy_sprite = select_side_from_image(loaded_def_e, "enemy")
                    self.enemy_element = element_from_sprite_path("sprites/sprite10.png")
                    # get player stats
                self.player_name = getattr(p, "name", getattr(p, "player_name", self.player_name))
                self.player_level = getattr(p, "level", getattr(p, "lvl", self.player_level))
                self.player_hp = getattr(p, "hp", self.player_hp)
                self.player_max = getattr(p, "max_hp", getattr(p, "maxhp", self.player_max))
                # Prefer showing the actual first monster from the player's bag (if any)
                try:
                    if gm is not None:
                        monsters = getattr(gm.bag, "_monsters_data", []) or []
                        if len(monsters) > 0:
                            m0 = monsters[0]
                            # m0 is expected to be a dict-like object from Bag
                            self.player_name = m0.get("name", self.player_name)
                            try:
                                self.player_level = int(m0.get("level", self.player_level))
                            except Exception:
                                pass
                            try:
                                self.player_hp = int(m0.get("hp", self.player_hp))
                            except Exception:
                                pass
                            try:
                                self.player_max = int(m0.get("max_hp", self.player_max))
                            except Exception:
                                pass
                            try:
                                self.player_attack = int(m0.get("attack", 12))
                            except Exception:
                                pass
                            # If the bag provides a sprite_path and no player_sprite was already set, try to load it
                            try:
                                spath = m0.get("sprite_path")
                                if spath and not self.player_sprite:
                                    tmp = resource_manager.get_image(spath)
                                    if tmp:
                                        self.player_sprite = tmp
                                self.player_element = m0.get("element", element_from_sprite_path(spath))
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            pass

        # derive thumbnails for name boxes (menu_sprites). Prefer explicit attributes if present
        def derive_thumb_from_sprite(sprite_path, default_idx=1):
            # 根據 sprite_path 取數字對應 menusprite
            if sprite_path:
                m = re.search(r"(\d+)", sprite_path)
                if m:
                    idx = m.group(1)
                    cand = f"menu_sprites/menusprite{idx}.png"
                    try:
                        return resource_manager.get_image(cand)
                    except Exception:
                        pass
            # default
            try:
                return resource_manager.get_image(f"menu_sprites/menusprite{default_idx}.png")
            except Exception:
                return None

        # 依據實際派出精靈的 sprite_path 來決定縮圖
        # 取得實際 battle sprite path（優先用 battle scene 內已選用的 sprite 路徑）
        player_sprite_path = None
        enemy_sprite_path = None
        # player_sprite_path 以 self.player_sprite 來源為主
        try:
            if hasattr(self, "player_sprite") and self.player_sprite is not None:
                # 從 gm.player.sprite_path 取得
                if gm and getattr(gm, "player", None) is not None:
                    player_sprite_path = getattr(gm.player, "sprite_path", None)
        except Exception:
            pass
        # enemy_sprite_path 以 self.enemy_sprite 來源為主
        try:
            if hasattr(self, "enemy_sprite") and self.enemy_sprite is not None:
                if target is not None:
                    enemy_sprite_path = getattr(target, "sprite_path", None)
        except Exception:
            pass
        self.player_thumb = derive_thumb_from_sprite(player_sprite_path, default_idx=1)
        self.enemy_thumb = derive_thumb_from_sprite(enemy_sprite_path, default_idx=10)

        # bind action button callbacks now that enter() has set stats
        # Buttons use on_click with no args, so wrap calls
        def make_click(i):
            def cb():
                if i == 0:
                    # Fight
                    if self.turn != "player":
                        return
                    dmg = self.player_attack
                    # element-based effectiveness using cached element values
                    player_elem = getattr(self, "player_element", "Normal")
                    enemy_elem = getattr(self, "enemy_element", "Normal")
                    mult = effectiveness_multiplier(player_elem, enemy_elem)
                    dmg = int(dmg * mult * self.player_attack_multiplier)
                    # apply player's damage immediately and show player's message
                    self.pending_player_damage = dmg
                    # feedback on effectiveness
                    eff_msg = ""
                    if mult > 1.0:
                        eff_msg = " It's super effective!"
                    elif mult < 1.0:
                        eff_msg = " It's not very effective..."
                    self.pending_player_msg = f"Player do {dmg} damage.{eff_msg}"
                    # apply damage now
                    self.enemy_hp = max(0, self.enemy_hp - dmg)
                    self.info = self.pending_player_msg
                    Logger.info(f"Battle: player attacked enemy for {dmg}, enemy_hp={self.enemy_hp}")
                    if self.enemy_hp <= 0:
                        self.info += " Enemy defeated!"
                        # Award experience based on enemy level
                        enemy_level = self.enemy_max  # Use enemy_max as a proxy for level (or get from target)
                        exp_awarded = enemy_level * 5  # Give 5 exp per enemy level
                        self.gain_exp_and_levelup(exp_awarded)
                        try:
                            target = getattr(scene_manager, "battle_target", None)
                            if getattr(target, "is_wild", False):
                                gm = getattr(target, "game_manager", None)
                                if gm is not None:
                                    monster = {
                                        "name": getattr(target, "name", "Unknown"),
                                        "hp": getattr(target, "max_hp", self.enemy_max),
                                        "max_hp": getattr(target, "max_hp", self.enemy_max),
                                        "level": getattr(target, "level", 1),
                                        "sprite_path": getattr(target, "sprite_path", None),
                                        "element": getattr(target, "element", "Normal"),
                                        "exp": 0,
                                        "exp_to_next_level": getattr(target, "level", 1) ** 2 * 10,
                                    }
                                    try:
                                        gm.bag.add_monster(monster)
                                        self.info += " Added to bag!"
                                    except Exception as e:
                                        Logger.warning(f"Failed to add wild to bag: {e}")
                        except Exception:
                            pass
                        # Sync HP before leaving battle
                        self.sync_pokemon_hp_to_bag()
                        scene_manager.change_scene("game")
                        return
                    # schedule enemy follow-up after showing player's message
                    self.message_phase = 2
                    self.message_timer = 2.0
                    self.turn = "processing"
                elif i == 1:
                    # Items: open items overlay
                    self.show_items_overlay_func()
                elif i == 2:
                    # Pokemon: open Pokemon switch overlay
                    self.show_pokemon_overlay()
                elif i == 3:
                    self.info = "Player ran away!"
                    Logger.info("Battle: player ran away")
                    # Sync HP before leaving battle
                    self.sync_pokemon_hp_to_bag()
                    scene_manager.change_scene("game")
            return cb

        for idx, btn in enumerate(self.action_buttons):
            btn.on_click = make_click(idx)

    @override
    def exit(self) -> None:
        # Sync Pokemon HP before exiting battle
        self.sync_pokemon_hp_to_bag()
        # cleanup if needed
        if hasattr(scene_manager, "battle_target"):
            delattr(scene_manager, "battle_target")

    @override
    def update(self, dt: float) -> None:
        # On enemy turn, perform simple attack and switch back
        # update UI buttons
        for b in self.action_buttons:
            try:
                b.update(dt)
            except Exception:
                pass
        # If we are processing a message sequence (enemy-first then player), handle phases
        if self.message_phase != 0:
            try:
                self.message_timer = max(0.0, self.message_timer - dt)
            except Exception:
                self.message_timer = 0.0
            if self.message_timer > 0.0:
                return
            # After showing player's message, perform enemy follow-up attack
            if self.message_phase == 2:
                dmg = self.enemy_attack
                # element-based effectiveness for enemy attack
                enemy_elem = getattr(self, "enemy_element", "Normal")
                player_elem = getattr(self, "player_element", "Normal")
                mult = effectiveness_multiplier(enemy_elem, player_elem)
                dmg = int(dmg * mult * self.enemy_attack_multiplier)
                self.player_hp = max(0, self.player_hp - dmg)
                # Sync HP to bag immediately after damage
                self.sync_pokemon_hp_to_bag()
                eff_msg = ""
                if mult > 1.0:
                    eff_msg = " It's super effective!"
                elif mult < 1.0:
                    eff_msg = " It's not very effective..."
                self.info = f"Enemy hits Player for {dmg}!{eff_msg} What will Player do next?"
                Logger.info(f"Battle: enemy attacked player for {dmg} (mult={mult}), player_hp={self.player_hp}")
                if self.player_hp <= 0:
                    self.info += " Player defeated!"
                    # HP already synced above, but sync again for safety
                    self.sync_pokemon_hp_to_bag()
                    scene_manager.change_scene("game")
                    return
                # sequence complete; return control to player
                self.message_phase = 0
                self.message_timer = 0.0
                self.pending_player_damage = 0
                self.pending_player_msg = ""
                self.turn = "player"
                return

    @override
    def draw(self, screen: pg.Surface) -> None:
        # Draw background image if available
        if self.bg_img:
            try:
                bg = pg.transform.scale(self.bg_img, (GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT))
                screen.blit(bg, (0, 0))
            except Exception:
                screen.fill((30, 30, 60))
        else:
            screen.fill((30, 30, 60))

        # Draw enemy and player sprites (if available), positioned to match
        # layout in attachment (centered and more spread horizontally).
        # We only change display positions here.
        sprite_w, sprite_h = 180, 180
        center_x = GameSettings.SCREEN_WIDTH // 2
        center_y = GameSettings.SCREEN_HEIGHT // 2 - 40
        # Enemy placed to the right of center, slightly higher
        ex = center_x + 80
        ey = center_y - 160
        if self.enemy_sprite:
            try:
                # 使用上方的 (sprite_w, sprite_h) 對敵方精靈做縮放，控制顯示大小
                es = pg.transform.scale(self.enemy_sprite, (sprite_w, sprite_h))
                # 將縮放後的敵方精靈繪製到畫面上，位置由 (ex, ey) 決定
                screen.blit(es, (ex, ey))
            except Exception:
                pg.draw.rect(screen, (150, 200, 150), (ex, ey, sprite_w, sprite_h))
        else:
            pg.draw.rect(screen, (150, 200, 150), (ex, ey, sprite_w, sprite_h))


        # Player placed to the left of center, slightly lower
        px = center_x - 250
        py = center_y + 20
        if self.player_sprite:
            try:
                # 使用上方的 (sprite_w, sprite_h) 對我方精靈做縮放，控制顯示大小
                ps = pg.transform.scale(self.player_sprite, (sprite_w+50, sprite_h+50))
                # 將縮放後的我方精靈繪製到畫面上，位置由 (px, py) 決定
                screen.blit(ps, (px, py))
            except Exception:
                pg.draw.rect(screen, (100, 180, 200), (px, py, sprite_w, sprite_h))
        else:
            pg.draw.rect(screen, (100, 180, 200), (px, py, sprite_w, sprite_h))

        # Draw name boxes above HP like the screenshot
        # Enemy name box (top-right)
        name_box_w, name_box_h = 300, 80 
        enemy_name_x = GameSettings.SCREEN_WIDTH - name_box_w - 20
        enemy_name_y = 12
        # use banner image for the name box background
        if self.banner_img:
            try:
                nb = pg.transform.scale(self.banner_img, (name_box_w, name_box_h))
                screen.blit(nb, (enemy_name_x, enemy_name_y))
            except Exception:
                pg.draw.rect(screen, (245, 235, 200), (enemy_name_x, enemy_name_y, name_box_w, name_box_h))
        elif self.name_frame:
            try:
                nf = pg.transform.scale(self.name_frame, (name_box_w, name_box_h))
                screen.blit(nf, (enemy_name_x, enemy_name_y))
            except Exception:
                pg.draw.rect(screen, (245, 235, 200), (enemy_name_x, enemy_name_y, name_box_w, name_box_h))
        else:
            pg.draw.rect(screen, (245, 235, 200), (enemy_name_x, enemy_name_y, name_box_w, name_box_h))
        # --- 優化敵方資訊框 ---
        thumb_size = name_box_h - 8
        text_x_offset = 8
        thumb_y = enemy_name_y - 12
        if self.enemy_thumb:
            try:
                thumb_s = pg.transform.scale(self.enemy_thumb, (thumb_size, thumb_size))
                tx = enemy_name_x + 16
                screen.blit(thumb_s, (tx, thumb_y))
                text_x_offset += thumb_size + 14
            except Exception:
                pass
        # 名字
        name_font = pg.font.SysFont(None, 24, bold=True)
        name_txt = name_font.render(str(self.enemy_name), True, (10,10,10))
        screen.blit(name_txt, (enemy_name_x + text_x_offset, enemy_name_y + 6))
        # element dot next to enemy name
        color = (120,120,120)
        elem = getattr(self, "enemy_element", "Normal")
        if elem == "Grass":
            color = (30, 180, 60)
        elif elem == "Fire":
            color = (220, 60, 40)
        elif elem == "Water":
            color = (50, 100, 220)
        dot_x = enemy_name_x + text_x_offset + name_txt.get_width() + 8
        dot_y = enemy_name_y + 10
        pg.draw.circle(screen, color, (dot_x, dot_y), 6)
        # 等級直接顯示在右上角
        enemy_lv = getattr(self, "enemy_level", 1)
        lv_font = pg.font.SysFont(None, 24, bold=True)
        lv_txt = lv_font.render(f"Lv{int(enemy_lv)}", True, (40,40,40))
        screen.blit(lv_txt, (enemy_name_x + name_box_w - lv_txt.get_width() - 10, enemy_name_y + 6))
        # HP bar 緊貼在名字下方
        # HP條長度維持原本比例，不拉長
        hp_w = 180
        hp_h = 10
        hp_x = enemy_name_x + text_x_offset
        hp_y = enemy_name_y + 6 + name_txt.get_height() + 6
        pg.draw.rect(screen, (120,120,120), (hp_x, hp_y, hp_w, hp_h))
        if self.enemy_max > 0:
            fill = int(hp_w * (self.enemy_hp / max(1, self.enemy_max)))
        else:
            fill = 0
        pg.draw.rect(screen, (40,200,40), (hp_x, hp_y, fill, hp_h))
        # HP 數字
        hp_font = pg.font.SysFont(None, 16)
        hp_txt = hp_font.render(f"{self.enemy_hp}/{self.enemy_max}", True, (30,30,30))
        screen.blit(hp_txt, (hp_x, hp_y + hp_h + 2))


        # Player name box (bottom-left, above player sprite)
        player_name_x = 20
        player_name_y = GameSettings.SCREEN_HEIGHT - 220  # 上移40px，避免被底部UI遮住
        if self.banner_img:
            try:
                nb2 = pg.transform.scale(self.banner_img, (name_box_w, name_box_h))
                screen.blit(nb2, (player_name_x, player_name_y))
            except Exception:
                pg.draw.rect(screen, (245, 235, 200), (player_name_x, player_name_y, name_box_w, name_box_h))
        elif self.name_frame:
            try:
                nf2 = pg.transform.scale(self.name_frame, (name_box_w, name_box_h))
                screen.blit(nf2, (player_name_x, player_name_y))
            except Exception:
                pg.draw.rect(screen, (245, 235, 200), (player_name_x, player_name_y, name_box_w, name_box_h))
        else:
            pg.draw.rect(screen, (245, 235, 200), (player_name_x, player_name_y, name_box_w, name_box_h))
        # --- 優化我方資訊框 ---
        thumb_size = name_box_h - 8
        p_text_x_offset = 8
        p_thumb_y = player_name_y - 12
        if self.player_thumb:
            try:
                p_thumb_s = pg.transform.scale(self.player_thumb, (thumb_size, thumb_size))
                ptx = player_name_x + 16
                screen.blit(p_thumb_s, (ptx, p_thumb_y))
                p_text_x_offset += thumb_size + 4
            except Exception:
                pass
        # 名字
        p_name_font = pg.font.SysFont(None, 24, bold=True)
        p_name_txt = p_name_font.render(str(self.player_name), True, (10,10,10))
        screen.blit(p_name_txt, (player_name_x + p_text_x_offset, player_name_y + 6))
        # element dot next to player name
        p_color = (120,120,120)
        p_elem = getattr(self, "player_element", "Normal")
        if p_elem == "Grass":
            p_color = (30, 180, 60)
        elif p_elem == "Fire":
            p_color = (220, 60, 40)
        elif p_elem == "Water":
            p_color = (50, 100, 220)
        p_dot_x = player_name_x + p_text_x_offset + p_name_txt.get_width() + 8
        p_dot_y = player_name_y + 10
        pg.draw.circle(screen, p_color, (p_dot_x, p_dot_y), 6)
        # 等級直接顯示在右上角
        player_lv = getattr(self, "player_level", 1)
        p_lv_font = pg.font.SysFont(None, 24, bold=True)
        p_lv_txt = p_lv_font.render(f"Lv{int(player_lv)}", True, (40,40,40))
        screen.blit(p_lv_txt, (player_name_x + name_box_w - p_lv_txt.get_width() - 10, player_name_y + 6))
        # HP bar 緊貼在名字下方
        php_w = name_box_w - p_text_x_offset - 16
        php_h = 10
        php_x = player_name_x + p_text_x_offset
        php_y = player_name_y + 6 + p_name_txt.get_height() + 6
        pg.draw.rect(screen, (120,120,120), (php_x, php_y, php_w, php_h))
        if self.player_max > 0:
            pfill = int(php_w * (self.player_hp / max(1, self.player_max)))
        else:
            pfill = 0
        pg.draw.rect(screen, (40,200,40), (php_x, php_y, pfill, php_h))
        # HP 數字
        p_hp_font = pg.font.SysFont(None, 16)
        p_hp_txt = p_hp_font.render(f"{self.player_hp}/{self.player_max}", True, (30,30,30))
        screen.blit(p_hp_txt, (php_x, php_y + php_h + 2))
        
        # EXP bar (under HP bar, half height, blue color)
        pexp_w = php_w  # Same length as HP bar
        pexp_h = 5  # Half height of HP bar
        pexp_y = php_y + php_h + 16  # Below HP bar with some spacing
        pg.draw.rect(screen, (80, 80, 80), (php_x, pexp_y, pexp_w, pexp_h))  # Gray background
        
        # Get current Pokemon's exp info (player's current active Pokemon)
        target = getattr(scene_manager, "battle_target", None)
        if target:
            gm = getattr(target, "game_manager", None)
            if gm:
                monsters = getattr(gm.bag, "_monsters_data", []) or []
                current_idx = getattr(self, "current_pokemon_index", 0)
                if current_idx < len(monsters):
                    current_mon = monsters[current_idx]
                    mon_exp = current_mon.get("exp", 0)
                    mon_exp_to_next = current_mon.get("exp_to_next_level", 100)
                    if mon_exp_to_next > 0:
                        pexp_fill = int(pexp_w * (mon_exp / max(1, mon_exp_to_next)))
                    else:
                        pexp_fill = 0
                    pg.draw.rect(screen, (50, 100, 220), (php_x, pexp_y, pexp_fill, pexp_h))  # Blue fill
                    
                    # EXP text
                    pexp_font = pg.font.SysFont(None, 14)
                    pexp_txt = pexp_font.render(f"{mon_exp}/{mon_exp_to_next}", True, (30, 30, 30))
                    screen.blit(pexp_txt, (php_x, pexp_y + pexp_h + 2))


        # Draw bottom UI frame
        panel_h = 120
        panel_y = GameSettings.SCREEN_HEIGHT - panel_h
        if self.ui_frame:
            try:
                frame = pg.transform.scale(self.ui_frame, (GameSettings.SCREEN_WIDTH, panel_h))
                screen.blit(frame, (0, panel_y))
            except Exception:
                pg.draw.rect(screen, (20,20,20), (0, panel_y, GameSettings.SCREEN_WIDTH, panel_h))
        else:
            pg.draw.rect(screen, (20,20,20), (0, panel_y, GameSettings.SCREEN_WIDTH, panel_h))

        # Draw action buttons (4) using Button components (shows hover/pressed)
        labels = ["Fight", "Items", "Pokemon", "Run"]
        for i, btn in enumerate(self.action_buttons):
            try:
                btn.draw(screen)
            except Exception:
                # fallback draw
                r = self.button_rects[i]
                if self.button_img:
                    try:
                        bsurf = pg.transform.scale(self.button_img, (r.w, r.h))
                        screen.blit(bsurf, (r.x, r.y))
                    except Exception:
                        pg.draw.rect(screen, (240,240,240), r)
                else:
                    pg.draw.rect(screen, (240,240,240), r)
            # draw label centered
            rect = self.button_rects[i]
            txt = self.font.render(labels[i], True, (20,20,20))
            tx = rect.x + (rect.w - txt.get_width()) // 2
            ty = rect.y + (rect.h - txt.get_height()) // 2
            screen.blit(txt, (tx, ty))

        # Info text (left of panel)
        info_txt = self.font.render(self.info, True, (255,255,255))
        screen.blit(info_txt, (20, panel_y + 12))
        
        # Draw Pokemon overlay if active
        if self.show_overlay:
            self.draw_pokemon_overlay(screen)
        
        # Draw Items overlay if active
        if self.show_items_overlay:
            self.draw_items_overlay(screen)

    def draw_pokemon_overlay(self, screen: pg.Surface):
        """Draw the Pokemon switch overlay"""
        # Semi-transparent background
        overlay_bg = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT))
        overlay_bg.set_alpha(180)
        overlay_bg.fill((0, 0, 0))
        screen.blit(overlay_bg, (0, 0))
        
        # Get overlay rect
        overlay_rect = self.get_overlay_rect()
        
        # Draw overlay panel background
        if self.ui_frame:
            try:
                frame = pg.transform.scale(self.ui_frame, (overlay_rect.w, overlay_rect.h))
                screen.blit(frame, (overlay_rect.x, overlay_rect.y))
            except Exception:
                pg.draw.rect(screen, (240, 235, 220), overlay_rect)
                pg.draw.rect(screen, (100, 80, 60), overlay_rect, 3)
        else:
            pg.draw.rect(screen, (240, 235, 220), overlay_rect)
            pg.draw.rect(screen, (100, 80, 60), overlay_rect, 3)
        
        # Title
        title_font = pg.font.Font(None, 36)
        title_txt = title_font.render("Switch Pokemon", True, (0, 0, 0))
        title_x = overlay_rect.x + (overlay_rect.w - title_txt.get_width()) // 2
        screen.blit(title_txt, (title_x, overlay_rect.y + 15))
        
        # Get monsters from bag
        target = getattr(scene_manager, "battle_target", None)
        monsters = []
        if target:
            gm = getattr(target, "game_manager", None)
            if gm:
                monsters = getattr(gm.bag, "_monsters_data", []) or []
        
        # Content area
        content_x = overlay_rect.x + 20
        content_y = overlay_rect.y + 60
        content_w = overlay_rect.w - 40
        content_h = overlay_rect.h - 80
        
        # Clear switch buttons list
        self.switch_buttons = []
        
        # Draw monsters with scroll
        row_h = 80
        visible_rows = content_h // row_h
        total_rows = len(monsters)
        self.overlay_max_scroll = max(0, (total_rows - visible_rows) * row_h)
        
        start_idx = self.overlay_scroll // row_h
        end_idx = min(total_rows, start_idx + visible_rows + 1)
        offset_px = self.overlay_scroll % row_h
        
        # Clip to content area
        clip_rect = pg.Rect(content_x, content_y, content_w, content_h)
        prev_clip = screen.get_clip()
        screen.set_clip(clip_rect)
        
        for idx in range(start_idx, end_idx):
            if idx >= len(monsters):
                break
            
            m = monsters[idx]
            row_y = content_y + (idx - start_idx) * row_h - offset_px
            
            # Skip if not visible
            if row_y + row_h < content_y or row_y > content_y + content_h:
                continue
            
            # Draw banner background
            banner_w = content_w - 100  # Leave space for button
            if self.banner_img:
                try:
                    banner = pg.transform.scale(self.banner_img, (banner_w, row_h - 10))
                    screen.blit(banner, (content_x, row_y))
                except Exception:
                    pg.draw.rect(screen, (245, 235, 200), (content_x, row_y, banner_w, row_h - 10))
            else:
                pg.draw.rect(screen, (245, 235, 200), (content_x, row_y, banner_w, row_h - 10))
            
            # Thumbnail
            thumb_size = row_h - 20
            thumb_x = content_x + 10
            thumb_y = row_y + 5
            
            try:
                sprite_path = m.get("sprite_path") if isinstance(m, dict) else None
                if sprite_path:
                    # Try to get menu sprite
                    match = re.search(r"(\d+)", sprite_path)
                    if match:
                        idx_num = match.group(1)
                        thumb_path = f"menu_sprites/menusprite{idx_num}.png"
                        try:
                            img = resource_manager.get_image(thumb_path)
                            img = pg.transform.scale(img, (thumb_size, thumb_size))
                            screen.blit(img, (thumb_x, thumb_y))
                        except Exception:
                            pass
            except Exception:
                pass
            
            # Pokemon info
            text_x = thumb_x + thumb_size + 10
            name = m.get("name", "Unknown") if isinstance(m, dict) else str(m)
            lvl = m.get("level", 1) if isinstance(m, dict) else 1
            hp = m.get("hp", 0) if isinstance(m, dict) else 0
            maxhp = m.get("max_hp", hp) if isinstance(m, dict) else hp
            
            # Name and level
            name_font = pg.font.Font(None, 24)
            name_txt = name_font.render(f"{name} Lv{int(lvl)}", True, (10, 10, 10))
            screen.blit(name_txt, (text_x, row_y + 10))
            
            # HP bar
            hp_w = 150
            hp_h = 10
            hp_x = text_x
            hp_y = row_y + 35
            pg.draw.rect(screen, (120, 120, 120), (hp_x, hp_y, hp_w, hp_h))
            if maxhp > 0:
                fill = int(hp_w * (hp / max(1, maxhp)))
            else:
                fill = 0
            hp_color = (40, 200, 40) if hp > 0 else (200, 40, 40)
            pg.draw.rect(screen, hp_color, (hp_x, hp_y, fill, hp_h))
            
            # HP text
            hp_font = pg.font.Font(None, 16)
            hp_txt = hp_font.render(f"{hp}/{maxhp}", True, (30, 30, 30))
            screen.blit(hp_txt, (hp_x, hp_y + hp_h + 2))
            
            # Switch button
            btn_w = 80
            btn_h = 36
            btn_x = content_x + banner_w + 10
            btn_y = row_y + (row_h - 10 - btn_h) // 2
            btn_rect = pg.Rect(btn_x, btn_y, btn_w, btn_h)
            
            # Don't show button for current Pokemon or fainted Pokemon
            can_switch = (idx != self.current_pokemon_index and hp > 0)
            
            if can_switch:
                # Draw button
                if self.button_img:
                    try:
                        btn_surf = pg.transform.scale(self.button_img, (btn_w, btn_h))
                        screen.blit(btn_surf, (btn_x, btn_y))
                    except Exception:
                        pg.draw.rect(screen, (200, 200, 200), btn_rect)
                        pg.draw.rect(screen, (100, 100, 100), btn_rect, 2)
                else:
                    pg.draw.rect(screen, (200, 200, 200), btn_rect)
                    pg.draw.rect(screen, (100, 100, 100), btn_rect, 2)
                
                # Button text
                btn_font = pg.font.Font(None, 20)
                btn_txt = btn_font.render("Switch", True, (20, 20, 20))
                btn_txt_x = btn_x + (btn_w - btn_txt.get_width()) // 2
                btn_txt_y = btn_y + (btn_h - btn_txt.get_height()) // 2
                screen.blit(btn_txt, (btn_txt_x, btn_txt_y))
                
                # Add to clickable buttons
                self.switch_buttons.append((btn_rect, idx))
            else:
                # Show "Active" or "Fainted" label
                label_font = pg.font.Font(None, 18)
                if idx == self.current_pokemon_index:
                    label_txt = label_font.render("Active", True, (40, 120, 40))
                else:
                    label_txt = label_font.render("Fainted", True, (120, 40, 40))
                label_x = btn_x + (btn_w - label_txt.get_width()) // 2
                label_y = btn_y + (btn_h - label_txt.get_height()) // 2
                screen.blit(label_txt, (label_x, label_y))
        
        screen.set_clip(prev_clip)
        
        # Draw scroll bar if needed
        if total_rows > visible_rows:
            bar_w = 8
            bar_h = int(visible_rows * row_h / max(1, total_rows) * content_h)
            bar_h = min(bar_h, content_h)
            if self.overlay_max_scroll > 0:
                bar_y = content_y + int(self.overlay_scroll * (content_h - bar_h) / self.overlay_max_scroll)
            else:
                bar_y = content_y
            pg.draw.rect(screen, (180, 180, 180), (content_x + content_w - bar_w - 5, content_y, bar_w, content_h))
            pg.draw.rect(screen, (80, 80, 80), (content_x + content_w - bar_w - 5, bar_y, bar_w, bar_h))

    def handle_click(self, pos):
        if self.turn != "player":
            return
        # Check which action button was clicked
        if self.button_rects[0].collidepoint(pos):
            # Fight — apply player's damage immediately and schedule enemy follow-up
            dmg = self.player_attack
            self.pending_player_damage = dmg
            self.pending_player_msg = f"Player do {dmg} damage."
            self.enemy_hp = max(0, self.enemy_hp - dmg)
            self.info = self.pending_player_msg
            Logger.info(f"Battle: player attacked enemy for {dmg}, enemy_hp={self.enemy_hp}")
            if self.enemy_hp <= 0:
                self.info += " Enemy defeated!"
                try:
                    target = getattr(scene_manager, "battle_target", None)
                    if getattr(target, "is_wild", False):
                        gm = getattr(target, "game_manager", None)
                        if gm is not None:
                            monster = {
                                "name": getattr(target, "name", "Unknown"),
                                "hp": getattr(target, "max_hp", self.enemy_max),
                                "max_hp": getattr(target, "max_hp", self.enemy_max),
                                "level": getattr(target, "level", 1),
                                "sprite_path": getattr(target, "sprite_path", None)
                            }
                            try:
                                gm.bag.add_monster(monster)
                                self.info += " Added to bag!"
                            except Exception as e:
                                Logger.warning(f"Failed to add wild to bag: {e}")
                except Exception:
                    pass
                # Sync HP before leaving battle
                self.sync_pokemon_hp_to_bag()
                scene_manager.change_scene("game")
                return
            # schedule enemy follow-up after showing player's message
            self.message_phase = 2
            self.message_timer = 1.0
            self.turn = "processing"
        elif self.button_rects[1].collidepoint(pos):
            sdmg = 25
            self.pending_player_damage = sdmg
            self.pending_player_msg = "Emotional Damage! Ha Ha!"
            self.enemy_hp = max(0, self.enemy_hp - sdmg)
            self.info = self.pending_player_msg
            Logger.info(f"Battle: player used Special for {sdmg}, enemy_hp={self.enemy_hp}")
            if self.enemy_hp <= 0:
                self.info += " Enemy defeated!"
                try:
                    target = getattr(scene_manager, "battle_target", None)
                    if getattr(target, "is_wild", False):
                        gm = getattr(target, "game_manager", None)
                        if gm is not None:
                            monster = {
                                "name": getattr(target, "name", "Unknown"),
                                "hp": getattr(target, "max_hp", self.enemy_max),
                                "max_hp": getattr(target, "max_hp", self.enemy_max),
                                "level": getattr(target, "level", 1),
                                "sprite_path": getattr(target, "sprite_path", None)
                            }
                            try:
                                gm.bag.add_monster(monster)
                                self.info += " Added to bag!"
                            except Exception as e:
                                Logger.warning(f"Failed to add wild to bag: {e}")
                except Exception:
                    pass
                # Sync HP before leaving battle
                self.sync_pokemon_hp_to_bag()
                scene_manager.change_scene("game")
                return
            self.message_phase = 2
            self.message_timer = 1.0
            self.turn = "processing"
        elif self.button_rects[2].collidepoint(pos):
            # Pokemon: open Pokemon switch overlay
            self.show_pokemon_overlay()
        elif self.button_rects[3].collidepoint(pos):
            # Run
            self.info = "Player ran away!"
            Logger.info("Battle: player ran away")
            # Sync HP before leaving battle
            self.sync_pokemon_hp_to_bag()
            scene_manager.change_scene("game")

    def sync_pokemon_hp_to_bag(self):
        """Sync current Pokemon's HP back to the bag data"""
        try:
            target = getattr(scene_manager, "battle_target", None)
            if not target:
                return
            
            gm = getattr(target, "game_manager", None)
            if not gm:
                return
            
            monsters = getattr(gm.bag, "_monsters_data", []) or []
            if self.current_pokemon_index < len(monsters):
                current_mon = monsters[self.current_pokemon_index]
                if isinstance(current_mon, dict):
                    # Update HP in the bag
                    current_mon["hp"] = self.player_hp
                    Logger.info(f"Synced Pokemon HP: {current_mon.get('name', 'Unknown')} now has {self.player_hp} HP")
        except Exception as e:
            Logger.warning(f"Failed to sync Pokemon HP: {e}")

    def show_pokemon_overlay(self):
        """Open the Pokemon switch overlay"""
        if self.turn != "player":
            return
        # Sync current Pokemon HP before showing overlay
        self.sync_pokemon_hp_to_bag()
        self.show_overlay = True
        self.overlay_scroll = 0
        Logger.info("Opening Pokemon switch overlay")

    def close_pokemon_overlay(self):
        """Close the Pokemon switch overlay"""
        self.show_overlay = False
        self.overlay_scroll = 0
        Logger.info("Closing Pokemon switch overlay")

    def switch_pokemon(self, pokemon_index):
        """Switch to a different Pokemon and skip player turn"""
        if self.turn != "player":
            return
        
        # Sync current Pokemon HP before switching
        self.sync_pokemon_hp_to_bag()
        
        # Get game manager and bag
        target = getattr(scene_manager, "battle_target", None)
        if not target:
            return
        
        gm = getattr(target, "game_manager", None)
        if not gm:
            return
        
        monsters = getattr(gm.bag, "_monsters_data", []) or []
        
        # Can't switch to same Pokemon or invalid index
        if pokemon_index == self.current_pokemon_index or pokemon_index >= len(monsters):
            return
        
        # Check if Pokemon has enough HP to switch in
        new_pokemon = monsters[pokemon_index]
        if isinstance(new_pokemon, dict):
            hp = new_pokemon.get("hp", 0)
            if hp <= 0:
                self.info = "That Pokemon has fainted!"
                return
        
        # Perform the switch
        self.current_pokemon_index = pokemon_index
        
        # Update player stats based on new Pokemon
        if isinstance(new_pokemon, dict):
            self.player_name = new_pokemon.get("name", "Player")
            self.player_level = new_pokemon.get("level", 1)
            self.player_hp = new_pokemon.get("hp", 100)
            self.player_max = new_pokemon.get("max_hp", 100)
            self.player_attack = new_pokemon.get("attack", 12)
            # Update player element from Pokemon data
            self.player_element = new_pokemon.get("element", "Grass")
            
            sprite_path = new_pokemon.get("sprite_path")
            if sprite_path:
                try:
                    # Extract sprite number from path (works for both menu_sprites and sprites paths)
                    m = re.search(r"(\d+)", sprite_path)
                    if m:
                        sprite_num = m.group(1)
                        # Construct the battle sprite path (_pokemon version)
                        pokemon_path = f"sprites/sprite{sprite_num}_pokemon.png"
                        
                        Logger.info(f"Trying to load Pokemon battle sprite: {pokemon_path}")
                        
                        # Try _pokemon variant first (for battle back sprite)
                        pokemon_variants = [
                            pokemon_path,
                            f"sprites/sprite{sprite_num}_back.png",
                            f"sprites/sprite{sprite_num}_right.png",
                            f"sprites/sprite{sprite_num}.png"  # fallback to original
                        ]
                        loaded_sprite = None
                        for variant in pokemon_variants:
                            try:
                                loaded_sprite = resource_manager.get_image(variant)
                                if loaded_sprite:
                                    Logger.info(f"Successfully loaded battle sprite: {variant}")
                                    break
                            except Exception as e:
                                Logger.info(f"Failed to load {variant}: {e}")
                                continue
                        
                        if loaded_sprite:
                            self.player_sprite = loaded_sprite
                            # Also update thumbnail (use menu sprite)
                            cand = f"menu_sprites/menusprite{sprite_num}.png"
                            try:
                                self.player_thumb = resource_manager.get_image(cand)
                            except Exception:
                                pass
                except Exception:
                    pass
        
        # Close overlay
        self.close_pokemon_overlay()
        
        # Show switch message
        self.info = f"Go! {self.player_name}!"
        Logger.info(f"Switched to Pokemon: {self.player_name}")
        
        # Skip player turn - enemy attacks next
        self.message_phase = 2
        self.message_timer = 1.5  # Give player time to see switch message
        self.turn = "processing"

    def get_overlay_rect(self):
        """Get the rectangle for the Pokemon overlay"""
        overlay_w = 600
        overlay_h = 500
        overlay_x = (GameSettings.SCREEN_WIDTH - overlay_w) // 2
        overlay_y = (GameSettings.SCREEN_HEIGHT - overlay_h) // 2
        return pg.Rect(overlay_x, overlay_y, overlay_w, overlay_h)

    def gain_exp_and_levelup(self, exp_gained: int):
        """
        Give experience to the current active Pokemon and handle levelup.
        """
        from src.utils.definition import calculate_exp_for_level, check_evolution
        
        target = getattr(scene_manager, "battle_target", None)
        if not target:
            return
        
        gm = getattr(target, "game_manager", None)
        if not gm:
            return
        
        monsters = getattr(gm.bag, "_monsters_data", []) or []
        if self.current_pokemon_index >= len(monsters):
            return
        
        current_mon = monsters[self.current_pokemon_index]
        
        # Add experience
        current_mon["exp"] = current_mon.get("exp", 0) + exp_gained
        
        # Check for levelup
        levelup_messages = []
        evolution_occurred = False
        while current_mon["exp"] >= current_mon.get("exp_to_next_level", 100):
            current_mon["exp"] -= current_mon.get("exp_to_next_level", 100)
            current_mon["level"] = current_mon.get("level", 1) + 1
            
            # Recalculate stats based on new level
            new_level = current_mon["level"]
            base_hp = 20
            new_hp = base_hp + (new_level - 1) * 5
            new_attack = int(10 + (new_level - 1) * 1.5)
            
            # Increase current HP by the same amount as max_hp increased
            old_max_hp = current_mon.get("max_hp", new_hp)
            current_mon["max_hp"] = new_hp
            current_mon["hp"] = min(new_hp, current_mon.get("hp", 0) + (new_hp - old_max_hp))
            current_mon["attack"] = new_attack
            
            # Update battle scene stats if this is the active Pokemon
            self.player_max = new_hp
            self.player_hp = current_mon["hp"]
            self.player_attack = new_attack
            
            # Update next level exp requirement
            current_mon["exp_to_next_level"] = calculate_exp_for_level(new_level + 1)
            
            levelup_messages.append(f"{current_mon['name']} leveled up to {new_level}!")
            Logger.info(f"Battle: {current_mon['name']} leveled up to {new_level}")
            
            # Check for evolution
            old_name = current_mon.get("name", "Unknown")
            old_sprite = current_mon.get("sprite_path", "")
            evolution_result = check_evolution(old_sprite, new_level)
            if evolution_result:
                new_sprite, new_name = evolution_result
                current_mon["sprite_path"] = new_sprite
                current_mon["name"] = new_name
                levelup_messages.append(f"{old_name} evolved into {new_name}!")
                Logger.info(f"Evolution: {old_name} → {new_name}")
                evolution_occurred = True
                
                # Update battle scene sprites if this is the active Pokemon
                self.player_name = new_name
                # Reload player sprite for battle
                try:
                    import re
                    match = re.search(r"menusprite(\d+)", new_sprite)
                    if match:
                        sprite_num = match.group(1)
                        # Try different naming patterns for battle sprites
                        pokemon_variants = [
                            f"character/character{sprite_num}.png",
                            f"character/Pokemon{sprite_num}.png",
                            f"character/pokemon{sprite_num}.png",
                        ]
                        loaded_sprite = None
                        for variant in pokemon_variants:
                            try:
                                loaded_sprite = resource_manager.get_image(variant)
                                if loaded_sprite:
                                    Logger.info(f"Successfully loaded evolved sprite: {variant}")
                                    self.player_sprite = loaded_sprite
                                    break
                            except Exception:
                                continue
                        
                        # Update thumbnail
                        try:
                            self.player_thumb = resource_manager.get_image(new_sprite)
                        except Exception:
                            pass
                except Exception as e:
                    Logger.warning(f"Failed to update evolved sprite: {e}")
        
        # Update player HP in battle if leveled up
        if levelup_messages:
            self.player_max = current_mon.get("max_hp", self.player_max)
            self.player_hp = current_mon.get("hp", self.player_hp)
            self.info = " ".join(levelup_messages)
        else:
            self.info = f"Gained {exp_gained} experience points!"

    def show_items_overlay_func(self):
        """Open the items overlay"""
        if self.turn != "player":
            return
        self.show_items_overlay = True
        self.items_overlay_scroll = 0
        Logger.info("Opening items overlay")

    def close_items_overlay(self):
        """Close the items overlay"""
        self.show_items_overlay = False
        self.items_overlay_scroll = 0
        Logger.info("Closing items overlay")

    def use_item(self, item_index):
        """Use an item from the bag (item_index refers to filtered list)"""
        if self.turn != "player":
            return
        
        # Get game manager and bag
        target = getattr(scene_manager, "battle_target", None)
        if not target:
            return
        
        gm = getattr(target, "game_manager", None)
        if not gm:
            return
        
        all_items = getattr(gm.bag, "_items_data", []) or []
        # Filter to show only Pokeball and Potion items
        filtered_items = [item for item in all_items if "Potion" in item.get("name", "") or "Pokeball" in item.get("name", "")]
        
        if item_index >= len(filtered_items):
            return
        
        item = filtered_items[item_index]
        item_name = item.get("name", "")
        item_count = item.get("count", 0)
        
        if item_count <= 0:
            self.info = f"No {item_name} left!"
            return
        
        # Apply item effect based on name
        if item_name == "Heal Potion":
            # Heal player Pokemon by 20 HP
            heal_amount = 20
            old_hp = self.player_hp
            self.player_hp = min(self.player_max, self.player_hp + heal_amount)
            actual_heal = self.player_hp - old_hp
            self.info = f"Used Heal Potion! Restored {actual_heal} HP."
            Logger.info(f"Battle: used Heal Potion, healed {actual_heal} HP")
            # Sync HP to bag
            self.sync_pokemon_hp_to_bag()
            
        elif item_name == "Strength Potion":
            # Increase player attack multiplier to 1.5x
            self.player_attack_multiplier = 1.5
            self.info = "Used Strength Potion! Attack increased!"
            Logger.info("Battle: used Strength Potion, attack multiplier = 1.5")
            
        elif item_name == "Defense Potion":
            # Decrease enemy attack multiplier to 0.75x
            self.enemy_attack_multiplier = 0.75
            self.info = "Used Defense Potion! Enemy attack reduced!"
            Logger.info("Battle: used Defense Potion, enemy attack multiplier = 0.75")
        
        else:
            self.info = f"Used {item_name} but nothing happened."
            Logger.info(f"Battle: used unknown item {item_name}")
        
        # Decrease item count
        item["count"] -= 1
        
        # Close overlay
        self.close_items_overlay()
        
        # Enemy counterattack
        self.message_phase = 2
        self.message_timer = 2.0
        self.turn = "processing"

    def draw_items_overlay(self, screen: pg.Surface):
        """Draw the items overlay"""
        # Semi-transparent background
        overlay_bg = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT))
        overlay_bg.set_alpha(180)
        overlay_bg.fill((0, 0, 0))
        screen.blit(overlay_bg, (0, 0))
        
        # Get overlay rect
        overlay_rect = self.get_overlay_rect()
        
        # Draw overlay panel background
        if self.ui_frame:
            try:
                frame = pg.transform.scale(self.ui_frame, (overlay_rect.w, overlay_rect.h))
                screen.blit(frame, (overlay_rect.x, overlay_rect.y))
            except Exception:
                pg.draw.rect(screen, (240, 235, 220), overlay_rect)
                pg.draw.rect(screen, (100, 80, 60), overlay_rect, 3)
        else:
            pg.draw.rect(screen, (240, 235, 220), overlay_rect)
            pg.draw.rect(screen, (100, 80, 60), overlay_rect, 3)
        
        # Title
        title_font = pg.font.Font(None, 36)
        title_txt = title_font.render("Items", True, (0, 0, 0))
        title_x = overlay_rect.x + (overlay_rect.w - title_txt.get_width()) // 2
        screen.blit(title_txt, (title_x, overlay_rect.y + 15))
        
        # Get items from bag
        target = getattr(scene_manager, "battle_target", None)
        items = []
        if target:
            gm = getattr(target, "game_manager", None)
            if gm:
                all_items = getattr(gm.bag, "_items_data", []) or []
                # Filter to show only Pokeball and Potion items
                items = [item for item in all_items if "Potion" in item.get("name", "") or "Pokeball" in item.get("name", "")]
        
        # Content area
        content_x = overlay_rect.x + 20
        content_y = overlay_rect.y + 60
        content_w = overlay_rect.w - 40
        content_h = overlay_rect.h - 80
        
        # Clear item buttons list
        self.item_buttons = []
        
        # Draw items with scroll
        row_h = 80
        visible_rows = content_h // row_h
        total_rows = len(items)
        self.items_overlay_max_scroll = max(0, (total_rows - visible_rows) * row_h)
        
        start_idx = self.items_overlay_scroll // row_h
        end_idx = min(total_rows, start_idx + visible_rows + 1)
        offset_px = self.items_overlay_scroll % row_h
        
        # Clip to content area
        clip_rect = pg.Rect(content_x, content_y, content_w, content_h)
        prev_clip = screen.get_clip()
        screen.set_clip(clip_rect)
        
        if len(items) == 0:
            # No items message
            no_items_font = pg.font.Font(None, 32)
            no_items_txt = no_items_font.render("No items in bag!", True, (100, 100, 100))
            txt_x = content_x + (content_w - no_items_txt.get_width()) // 2
            txt_y = content_y + (content_h - no_items_txt.get_height()) // 2
            screen.blit(no_items_txt, (txt_x, txt_y))
        
        for idx in range(start_idx, end_idx):
            if idx >= len(items):
                break
            
            item = items[idx]
            row_y = content_y + (idx - start_idx) * row_h - offset_px
            
            # Skip if not visible
            if row_y + row_h < content_y or row_y > content_y + content_h:
                continue
            
            # Draw banner background
            banner_w = content_w - 120  # Leave space for button
            if self.banner_img:
                try:
                    banner = pg.transform.scale(self.banner_img, (banner_w, row_h - 10))
                    screen.blit(banner, (content_x, row_y))
                except Exception:
                    pg.draw.rect(screen, (245, 235, 200), (content_x, row_y, banner_w, row_h - 10))
            else:
                pg.draw.rect(screen, (245, 235, 200), (content_x, row_y, banner_w, row_h - 10))
            
            # Item info
            text_x = content_x + 15
            name = item.get("name", "Unknown")
            count = item.get("count", 0)
            
            item_font = pg.font.Font(None, 28)
            name_txt = item_font.render(f"{name} x{count}", True, (20, 20, 20))
            screen.blit(name_txt, (text_x, row_y + 10))
            
            # Item description based on name
            desc = ""
            if name == "Heal Potion":
                desc = "Restore 20 HP"
            elif name == "Strength Potion":
                desc = "Increase attack to 1.5x"
            elif name == "Defense Potion":
                desc = "Reduce enemy attack to 0.75x"
            
            desc_font = pg.font.Font(None, 22)
            desc_txt = desc_font.render(desc, True, (80, 80, 80))
            screen.blit(desc_txt, (text_x, row_y + 40))
            
            # Use button
            btn_w = 100
            btn_h = row_h - 20
            btn_x = content_x + banner_w + 10
            btn_y = row_y + 5
            use_btn_rect = pg.Rect(btn_x, btn_y, btn_w, btn_h)
            self.item_buttons.append((use_btn_rect, idx))
            
            # Draw button
            if self.button_img:
                try:
                    btn_surf = pg.transform.scale(self.button_img, (btn_w, btn_h))
                    screen.blit(btn_surf, (btn_x, btn_y))
                except Exception:
                    pg.draw.rect(screen, (200, 200, 200), use_btn_rect)
                    pg.draw.rect(screen, (100, 100, 100), use_btn_rect, 2)
            else:
                pg.draw.rect(screen, (200, 200, 200), use_btn_rect)
                pg.draw.rect(screen, (100, 100, 100), use_btn_rect, 2)
            
            # Button text
            btn_font = pg.font.Font(None, 24)
            btn_txt = btn_font.render("Use", True, (20, 20, 20))
            btn_txt_x = btn_x + (btn_w - btn_txt.get_width()) // 2
            btn_txt_y = btn_y + (btn_h - btn_txt.get_height()) // 2
            screen.blit(btn_txt, (btn_txt_x, btn_txt_y))
        
        # Restore previous clip
        screen.set_clip(prev_clip)
        
        # Close button
        close_w = 100
        close_h = 40
        close_x = overlay_rect.x + overlay_rect.w - close_w - 20
        close_y = overlay_rect.y + overlay_rect.h - close_h - 20
        close_rect = pg.Rect(close_x, close_y, close_w, close_h)
        
        if self.button_img:
            try:
                close_surf = pg.transform.scale(self.button_img, (close_w, close_h))
                screen.blit(close_surf, (close_x, close_y))
            except Exception:
                pg.draw.rect(screen, (220, 220, 220), close_rect)
                pg.draw.rect(screen, (100, 100, 100), close_rect, 2)
        else:
            pg.draw.rect(screen, (220, 220, 220), close_rect)
            pg.draw.rect(screen, (100, 100, 100), close_rect, 2)
        
        close_font = pg.font.Font(None, 24)
        close_txt = close_font.render("Close", True, (20, 20, 20))
        close_txt_x = close_x + (close_w - close_txt.get_width()) // 2
        close_txt_y = close_y + (close_h - close_txt.get_height()) // 2
        screen.blit(close_txt, (close_txt_x, close_txt_y))

    @override
    def handle_event(self, event: pg.event.Event) -> None:
        # Handle Pokemon overlay interactions first
        if self.show_overlay:
            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                # Check if clicking outside overlay to close
                overlay_rect = self.get_overlay_rect()
                if not overlay_rect.collidepoint(pos):
                    self.close_pokemon_overlay()
                    return
                
                # Check switch button clicks
                for btn_rect, pokemon_idx in self.switch_buttons:
                    if btn_rect.collidepoint(pos):
                        self.switch_pokemon(pokemon_idx)
                        return
            
            # Handle scroll wheel in overlay
            if event.type == pg.MOUSEWHEEL:
                self.overlay_scroll -= event.y * 32
                self.overlay_scroll = max(0, min(self.overlay_scroll, self.overlay_max_scroll))
            
            # Consume all events when overlay is open
            return
        
        # Handle Items overlay interactions
        if self.show_items_overlay:
            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                # Check if clicking outside overlay to close
                overlay_rect = self.get_overlay_rect()
                if not overlay_rect.collidepoint(pos):
                    self.close_items_overlay()
                    return
                
                # Check close button
                close_w = 100
                close_h = 40
                close_x = overlay_rect.x + overlay_rect.w - close_w - 20
                close_y = overlay_rect.y + overlay_rect.h - close_h - 20
                close_rect = pg.Rect(close_x, close_y, close_w, close_h)
                if close_rect.collidepoint(pos):
                    self.close_items_overlay()
                    return
                
                # Check use item button clicks
                for btn_rect, item_idx in self.item_buttons:
                    if btn_rect.collidepoint(pos):
                        self.use_item(item_idx)
                        return
            
            # Handle scroll wheel in overlay
            if event.type == pg.MOUSEWHEEL:
                self.items_overlay_scroll -= event.y * 32
                self.items_overlay_scroll = max(0, min(self.items_overlay_scroll, self.items_overlay_max_scroll))
            
            # Consume all events when overlay is open
            return
        
        # Accept mouse click for buttons
        if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            # prefer Button components' own on_click handlers to avoid duplicate logic
            for i, rect in enumerate(self.button_rects):
                if rect.collidepoint(pos):
                    try:
                        btn = self.action_buttons[i]
                        if getattr(btn, "on_click", None):
                            btn.on_click()
                    except Exception:
                        pass
                    return
