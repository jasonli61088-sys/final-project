import pygame as pg
from typing import TYPE_CHECKING
from src.utils import GameSettings
from src.core.services import resource_manager
from src.scenes.ui_control import Checkbox, Slider

if TYPE_CHECKING:
  from src.core.managers.game_manager import GameManager


class BackpackOverlay:
  """A simple backpack overlay that reads data from GameManager.bag
  and renders lists of monsters and items inside a given panel rectangle.
  The overlay does not manage persistence itself; it always reads from
  the provided GameManager instance so it's synchronized with saves/loads
  that update the manager.
  """

  def __init__(self, game_manager: "GameManager"):
    self.game_manager = game_manager
    # fonts
    try:
      self.title_font = pg.font.Font(None, 28)
      self.item_font = pg.font.Font(None, 20)
    except Exception:
      self.title_font = None
      self.item_font = None

    # Visuals
    self.padding = 12
    self.line_height = 48  # banner高度
    # banner asset
    try:
      self.banner_img = resource_manager.get_image("UI/raw/UI_Flat_Banner03a.png")
    except Exception:
      self.banner_img = None
    # 滾動狀態
    self.scroll_offset = 0
    self.max_scroll = 0
    self.scroll_speed = 32

  def update(self, dt: float) -> None:
    # nothing per-frame
    pass

  def handle_event(self, event):
    # 支援滑鼠滾輪滾動
    if event.type == pg.MOUSEWHEEL:
      self.scroll_offset -= event.y * self.scroll_speed
    if self.scroll_offset < 0:
      self.scroll_offset = 0
    if self.scroll_offset > self.max_scroll:
      self.scroll_offset = self.max_scroll

  def draw_content(self, screen: pg.Surface, panel_x: int, panel_y: int, panel_w: int, panel_h: int) -> None:
    """Draw the interior content of the backpack on the given panel rectangle.
    This function assumes the caller already drew the panel background and border.
    """
    bag = getattr(self.game_manager, "bag", None)
    monsters = []
    items = []
    if bag is not None:
      monsters = getattr(bag, "_monsters_data", []) or []
      items = getattr(bag, "_items_data", []) or []

    # Title
    # Title: show 'Bag' at top-left of panel
    try:
      # Bag title should be larger and capitalized
      title_font = pg.font.Font(None, 36)
      title_surf = title_font.render("Bag", True, (0, 0, 0))
      screen.blit(title_surf, (panel_x + self.padding, panel_y + self.padding))
    except Exception:
      pass

    # Calculate content area
    content_x = panel_x + self.padding
    content_y = panel_y + self.padding + 30
    content_w = panel_w - self.padding * 2
    content_h = panel_h - (self.padding * 2 + 30)

    # Split into two columns: monsters (left) and items (right)
    col_gap = 10
    col_w = (content_w - col_gap) // 2

    # Draw column titles
    try:
      # Monsters title: not bold, same size as Items (with colon)
      col_title_font = pg.font.Font(None, 24)
      m_title = col_title_font.render("Monsters:", True, (0, 0, 0))
      i_title = col_title_font.render("Items:", True, (0, 0, 0))
      screen.blit(m_title, (content_x, content_y))
      screen.blit(i_title, (content_x + col_w + col_gap, content_y))
    except Exception:
      pass

    # thumbnail sizes
    thumb_w, thumb_h = 40, 40

    # Draw monsters list with banner and scroll
    # increase row height so the banner (background) is slightly taller and
    # contains HP bar + numbers without overflow
    extra_row_h = 20
    row_h = self.line_height + extra_row_h
    y_offset = content_y + row_h
    visible_rows = max(1, (content_h - row_h) // row_h)
    total_rows = len(monsters)
    self.max_scroll = max(0, (total_rows - visible_rows) * row_h)
    start_idx = self.scroll_offset // row_h
    end_idx = min(total_rows, start_idx + visible_rows)
    offset_px = self.scroll_offset % row_h

    # 滾動裁切區域
    info_box_w = 260 + 40  # 跟戰鬥畫面一致
    info_box_h = row_h
    clip_rect = pg.Rect(content_x, y_offset, info_box_w, visible_rows * row_h)
    prev_clip = screen.get_clip()
    screen.set_clip(clip_rect)
    for idx in range(start_idx, end_idx):
      m = monsters[idx]
      row_y = y_offset + (idx - start_idx) * row_h - offset_px
      # banner鋪滿整行
      if self.banner_img:
        try:
          banner = pg.transform.scale(self.banner_img, (info_box_w, info_box_h))
          screen.blit(banner, (content_x, row_y))
        except Exception:
          pg.draw.rect(screen, (245, 235, 200), (content_x, row_y, info_box_w, info_box_h))
      else:
        pg.draw.rect(screen, (245, 235, 200), (content_x, row_y, info_box_w, info_box_h))

      # 怪獸資訊框（與戰鬥畫面一致）
      thumb_size = info_box_h - 8
      thumb_x = content_x + 6
      thumb_y = row_y + (info_box_h - thumb_size) // 2
      try:
        sprite_path = m.get("sprite_path") if isinstance(m, dict) else None
        if sprite_path:
          img = resource_manager.get_image(sprite_path)
          img = pg.transform.scale(img, (thumb_size, thumb_size))
          screen.blit(img, (thumb_x, thumb_y))
      except Exception:
        pass

      text_x_offset = thumb_x + thumb_size + 8
      name = m.get("name", "Unknown") if isinstance(m, dict) else str(m)
      name_font = pg.font.Font(None, 24)
      name_txt = name_font.render(str(name), True, (10, 10, 10))
      screen.blit(name_txt, (text_x_offset, row_y + 6))

      # 等級直接顯示在右上角
      lvl = m.get("level", 1) if isinstance(m, dict) else 1
      lv_font = pg.font.Font(None, 24)
      lv_font.set_bold(True)
      lv_txt = lv_font.render(f"Lv{int(lvl)}", True, (40, 40, 40))
      screen.blit(lv_txt, (content_x + info_box_w - lv_txt.get_width() - 10, row_y + 6))

      # HP bar（長度180，與戰鬥畫面一致）
      hp = m.get("hp", 0) if isinstance(m, dict) else 0
      maxhp = m.get("max_hp", hp) if isinstance(m, dict) else hp
      hp_w = 180
      hp_h = 10
      hp_x = text_x_offset
      hp_y = row_y + 6 + name_txt.get_height() + 6
      pg.draw.rect(screen, (120,120,120), (hp_x, hp_y, hp_w, hp_h))
      fill = int(hp_w * (hp / max(1, maxhp))) if maxhp > 0 else 0
      pg.draw.rect(screen, (40,200,40), (hp_x, hp_y, fill, hp_h))
      # HP 數字
      hp_font = pg.font.Font(None, 16)
      hp_txt = hp_font.render(f"{hp}/{maxhp}", True, (30,30,30))
      screen.blit(hp_txt, (hp_x, hp_y + hp_h + 2))
      
      # EXP bar (under HP bar, half height, blue color)
      exp = m.get("exp", 0) if isinstance(m, dict) else 0
      exp_to_next = m.get("exp_to_next_level", 100) if isinstance(m, dict) else 100
      exp_w = hp_w  # Same length as HP bar
      exp_h = 5  # Half height of HP bar
      exp_y = hp_y + hp_h + 12  # Below HP bar with some spacing
      pg.draw.rect(screen, (80, 80, 80), (hp_x, exp_y, exp_w, exp_h))  # Gray background
      exp_fill = int(exp_w * (exp / max(1, exp_to_next))) if exp_to_next > 0 else 0
      pg.draw.rect(screen, (50, 100, 220), (hp_x, exp_y, exp_fill, exp_h))  # Blue fill
      
      # EXP text
      exp_font = pg.font.Font(None, 14)
      exp_txt = exp_font.render(f"{exp}/{exp_to_next}", True, (30, 30, 30))
      screen.blit(exp_txt, (hp_x, exp_y + exp_h + 1))
    screen.set_clip(prev_clip)
    # 滾動條（可選）
    if total_rows > visible_rows:
      bar_h = int(visible_rows * (row_h) / max(1, total_rows) * (total_rows / visible_rows))
      bar_h = min(bar_h, content_h)
      # guard division by zero when max_scroll == 0
      if self.max_scroll > 0:
        bar_y = y_offset + int(self.scroll_offset * (content_h - bar_h) / max(1, self.max_scroll))
      else:
        bar_y = y_offset
      pg.draw.rect(screen, (180,180,180), (content_x + col_w - 8, y_offset, 8, content_h))
      pg.draw.rect(screen, (80,80,80), (content_x + col_w - 8, bar_y, 8, bar_h))

    # 使用方式：
    # 在主程式或 overlay 控制區呼叫 backpack_overlay.handle_event(event)
    # 例如：
    # for event in pg.event.get():
    #     backpack_overlay.handle_event(event)
    #     ...existing event handling...

    # Draw items list
    y_offset = content_y + self.line_height
    for it in items:
      name = it.get("name", "Unknown") if isinstance(it, dict) else str(it)
      count = it.get("count", None) if isinstance(it, dict) else None
      text = name
      if count is not None:
        text += f" x{count}"

      # Draw thumbnail if possible
      try:
        sprite_path = it.get("sprite_path") if isinstance(it, dict) else None
        if sprite_path:
          img = resource_manager.get_image(sprite_path)
          img = pg.transform.scale(img, (thumb_w, thumb_h))
          screen.blit(img, (content_x + col_w + col_gap, y_offset - 4))
      except Exception:
        pass

      try:
        if self.item_font:
          surf = self.item_font.render(text, True, (10, 10, 10))
          screen.blit(surf, (content_x + col_w + col_gap + thumb_w + 8, y_offset))
      except Exception:
        pass
      y_offset += max(self.line_height, thumb_h)

  def set_game_manager(self, gm: "GameManager") -> None:
    self.game_manager = gm


class SettingsOverlay:
  """Render simple settings controls (volume slider + fullscreen checkbox)
  inside the same panel area used by GameScene overlay. Uses the existing
  Checkbox and Slider UI controls (which expect absolute positions). We
  compute and assign those absolute positions each frame so the controls
  behave correctly inside the panel.
  """

  def __init__(self):
    # relative offsets inside the panel
    self.offset_checkbox = (20, 40)
    self.offset_slider = (20, 100)

    # create components with placeholder positions; we'll relocate them
    self.checkbox = Checkbox(0, 0, 20, checked=False)
    self.slider = Slider(0, 0, 200, 0, 100, int(GameSettings.AUDIO_VOLUME * 100))
    try:
      self.font = pg.font.Font(None, 24)
    except Exception:
      self.font = None

    # track last fullscreen state so we can toggle display when changed
    self._last_fullscreen_state = self.checkbox.checked

  def handle_event(self, event: pg.event.Event, panel_x: int, panel_y: int) -> None:
    # relocate controls before handling the event so event.pos matches
    self._relocate(panel_x, panel_y)
    self.checkbox.handle_event(event)
    self.slider.handle_event(event)

  def update(self, dt: float, panel_x: int, panel_y: int) -> None:
    # relocate and update
    self._relocate(panel_x, panel_y)
    self.checkbox.update(dt)
    self.slider.update(dt)

    # Apply fullscreen toggle if changed
    if self.checkbox.checked != self._last_fullscreen_state:
      self._last_fullscreen_state = self.checkbox.checked
      if self.checkbox.checked:
        pg.display.set_mode((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.FULLSCREEN)
      else:
        pg.display.set_mode((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT))

    # Sync volume
    GameSettings.AUDIO_VOLUME = self.slider.value / 100
    try:
      pg.mixer.music.set_volume(GameSettings.AUDIO_VOLUME)
    except Exception:
      pass

  def draw_content(self, screen: pg.Surface, panel_x: int, panel_y: int, panel_w: int, panel_h: int) -> None:
    self._relocate(panel_x, panel_y)
    # Title for settings: show 'setting' at top-left
    try:
      if self.font:
        title = self.font.render("setting", True, (0, 0, 0))
        screen.blit(title, (panel_x + 12, panel_y + 8))
    except Exception:
      pass

    # Draw checkbox and label
    self.checkbox.draw(screen)
    try:
      if self.font:
        label = self.font.render("Fullscreen", True, (0, 0, 0))
        screen.blit(label, (self.checkbox.rect.right + 10, self.checkbox.rect.y - 2))
    except Exception:
      pass

    # Draw slider and volume label
    self.slider.draw(screen)
    try:
      if self.font:
        vol_label = self.font.render(f"Volume: {int(self.slider.value)}", True, (0, 0, 0))
        screen.blit(vol_label, (self.slider.rect.x, self.slider.rect.y - 28))
    except Exception:
      pass

  def _relocate(self, panel_x: int, panel_y: int) -> None:
    # Position checkbox and slider to absolute coordinates inside panel
    cb_x = panel_x + self.offset_checkbox[0]
    cb_y = panel_y + self.offset_checkbox[1]
    self.checkbox.rect.topleft = (cb_x, cb_y)

    sl_x = panel_x + self.offset_slider[0]
    sl_y = panel_y + self.offset_slider[1]
    # slider.rect.width stays the same; recalc knob position from value
    self.slider.rect.topleft = (sl_x, sl_y)
    # recompute knob based on value
    ratio = (self.slider.value - self.slider.min_val) / max(1, (self.slider.max_val - self.slider.min_val))
    knob_x = sl_x + int(ratio * self.slider.rect.width) - self.slider.knob_rect.width // 2
    self.slider.knob_rect.topleft = (knob_x, sl_y - 6)