import pygame as pg

from src.utils import GameSettings
from src.sprites import BackgroundSprite
from src.scenes.scene import Scene
from src.interface.components import Button
from src.core.services import scene_manager, sound_manager, input_manager
from typing import override

# Simple Checkbox UI
class Checkbox:
	def __init__(self, x, y, label, checked=False):
		self.rect = pg.Rect(x, y, 32, 32)
		self.label = label
		# If checked not provided, sync with GameSettings.MUTED
		from src.utils import GameSettings as _GS
		self.checked = checked if checked is not None else _GS.MUTED
		# ensure label reflects current mute state if caller passed generic label
		if self.checked:
			self.label = "Mute On"
		else:
			self.label = "Mute Off"
		self.font = pg.font.SysFont(None, 32)
	def update(self, dt):
		# 互動區域只限方塊本身
		label_surf = self.font.render(self.label, True, (0,0,0))
		box_x = self.rect.x + label_surf.get_width() + 10
		box_rect = pg.Rect(box_x, self.rect.y, self.rect.w, self.rect.h)
		if box_rect.collidepoint(input_manager.mouse_pos):
			if input_manager.mouse_pressed(1):
				# toggle checked and update global mute + sound manager
				self.checked = not self.checked
				from src.core.services import sound_manager
				from src.utils import GameSettings
				if self.checked:
					GameSettings.MUTED = True
					try:
						sound_manager.pause_all()
					except Exception:
						pass
					self.label = "Mute On"
				else:
					GameSettings.MUTED = False
					try:
						sound_manager.resume_all()
					except Exception:
						pass
					self.label = "Mute Off"
	def draw(self, screen):
		# 文字在前，方塊在後，並可指定左側對齊座標
		align_x = getattr(self, 'align_x', self.rect.x)
		label_surf = self.font.render(self.label, True, (0,0,0))
		screen.blit(label_surf, (align_x, self.rect.y))
		box_x = align_x + label_surf.get_width() + 10
		box_rect = pg.Rect(box_x, self.rect.y, self.rect.w, self.rect.h)
		pg.draw.rect(screen, (200,200,200), box_rect)
		if self.checked:
			pg.draw.line(screen, (0,150,0), box_rect.topleft, box_rect.bottomright, 4)
			pg.draw.line(screen, (0,150,0), box_rect.topright, box_rect.bottomleft, 4)
		pg.draw.rect(screen, (0,0,0), box_rect, 2)

# Simple Slider UI
class Slider:
	def __init__(self, x, y, w, min_val, max_val, value):
		self.rect = pg.Rect(x, y, w, 8)
		self.min_val = min_val
		self.max_val = max_val
		self.value = value
		# store previous value to detect changes
		self._prev_value = value
		self.dragging = False
		self.font = pg.font.SysFont(None, 32)
		# knob_x 計算修正，確保 knob 初始時正好在桿子上
		if max_val != min_val:
			rel = (value - min_val) / (max_val - min_val)
			knob_x = int(x + rel * w - 8)
		else:
			knob_x = x - 8
		self.knob_rect = pg.Rect(knob_x, y-8, 16, 24)
	def update(self, dt):
		mouse = input_manager.mouse_pos
		# knob_rect 需根據 value 動態更新（每次 update 都重新定位）
		if self.max_val != self.min_val:
			knob_center_x = int(self.rect.x + (self.value-self.min_val)/(self.max_val-self.min_val)*self.rect.w)
		else:
			knob_center_x = self.rect.x
		self.knob_rect.x = knob_center_x - 8
		self.knob_rect.y = self.rect.y - 8
		if self.knob_rect.collidepoint(mouse):
			if input_manager.mouse_pressed(1):
				self.dragging = True
		if not input_manager.mouse_down(1):
			self.dragging = False
		if self.dragging:
			rel_x = max(self.rect.x, min(mouse[0], self.rect.x+self.rect.w))
			self.value = self.min_val + (rel_x-self.rect.x)/(self.rect.w)*(self.max_val-self.min_val)

		# If value changed, update global audio volume (0-100 -> 0.0-1.0)
		if hasattr(self, '_prev_value') and abs(self.value - self._prev_value) > 0.01:
			# update GameSettings and sound_manager volume
			try:
				GameSettings.AUDIO_VOLUME = max(0.0, min(1.0, float(self.value) / 100.0))
			except Exception:
				pass
			from src.core.services import sound_manager as _sm
			try:
				if getattr(_sm, 'current_bgm', None) is not None:
					_sm.current_bgm.set_volume(GameSettings.AUDIO_VOLUME)
			except Exception:
				pass
			self._prev_value = self.value
	def draw(self, screen):
		# Volume 標籤，左側對齊
		align_x = getattr(self, 'align_x', self.rect.x-90)
		label_surf = self.font.render("Volume", True, (0,0,0))
		screen.blit(label_surf, (align_x, self.rect.y-8))
		pg.draw.rect(screen, (180,180,180), self.rect)
		pg.draw.rect(screen, (0,0,0), self.rect, 2)
		# knob 位置根據 value 即時定位
		if self.max_val != self.min_val:
			knob_center_x = int(self.rect.x + (self.value-self.min_val)/(self.max_val-self.min_val)*self.rect.w)
		else:
			knob_center_x = self.rect.x
		knob_rect = pg.Rect(knob_center_x-8, self.rect.y-8, 16, 24)
		pg.draw.rect(screen, (100,100,255), knob_rect)
		pg.draw.rect(screen, (0,0,0), knob_rect, 2)
		val_surf = self.font.render(f"{self.value:.1f}", True, (0,0,0))
		screen.blit(val_surf, (self.rect.right+20, self.rect.y-8))

class SettingScene(Scene):
	background: BackgroundSprite
	back_button: Button

	checkbox: Checkbox
	slider: Slider

	def __init__(self):
		super().__init__()
		self.background = BackgroundSprite("UI/raw/UI_Flat_Frame03a.png")

		px, py = GameSettings.SCREEN_WIDTH // 2, GameSettings.SCREEN_HEIGHT * 3 // 4
		# Back button to return to main menu
		self.back_button = Button(
			"UI/button_back.png", "UI/button_back_hover.png",
			px - 50, py, 100, 100,
			lambda: scene_manager.change_scene("menu")
		)

		# Add a checkbox and slider
		self.checkbox = Checkbox(px-100, py-150, "Mute Off", False)
		# initialize slider value from GameSettings.AUDIO_VOLUME (0.0-1.0) -> 0-100
		self.slider = Slider(px-100, py-80, 200, 0, 100, GameSettings.AUDIO_VOLUME * 100)

	@override
	def enter(self) -> None:
		pass

	@override
	def exit(self) -> None:
		pass

	@override
	def update(self, dt: float) -> None:
		# allow ESC to go back as well
		if input_manager.key_pressed(pg.K_ESCAPE):
			scene_manager.change_scene("menu")
			return
		self.back_button.update(dt)
		self.checkbox.update(dt)
		self.slider.update(dt)

	@override
	def draw(self, screen: pg.Surface) -> None:
		# 縮小 overlay 視窗
		panel_w, panel_h = 500, 400
		panel_x = GameSettings.SCREEN_WIDTH // 2 - panel_w // 2
		panel_y = GameSettings.SCREEN_HEIGHT // 2 - panel_h // 2
		bg_img = self.background.image
		bg_img = pg.transform.scale(bg_img, (panel_w, panel_h))
		screen.blit(bg_img, (panel_x, panel_y))
		# 置中 back button, checkbox, slider
		self.back_button.hitbox.topleft = (panel_x + panel_w - 110, panel_y + panel_h - 110)
		self.back_button.draw(screen)
		cb_x = panel_x + 60
		cb_y = panel_y + 80
		self.checkbox.rect.topleft = (cb_x, cb_y)
		self.checkbox.align_x = cb_x
		self.checkbox.draw(screen)
		sl_x = panel_x + 60
		sl_y = cb_y + 80
		self.slider.rect.topleft = (sl_x + 90, sl_y)
		self.slider.align_x = cb_x
		self.slider.draw(screen)