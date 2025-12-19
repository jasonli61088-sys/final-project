import pygame
from typing import Callable, Optional

# src/scenes/ui_control.py
# 簡單的 Pygame Checkbox 與 Slider 控制元件
# 使用方式：將此檔放入專案並 import Checkbox, Slider


pygame.init()

# -------------------------
# Checkbox
# -------------------------
class Checkbox:
    def __init__(
        self,
        x: int,
        y: int,
        size: int = 20,
        label: str = "",
        font: Optional[pygame.font.Font] = None,
        checked: bool = False,
        callback: Optional[Callable[[bool], None]] = None,
    ):
        self.rect = pygame.Rect(x, y, size, size)
        self.size = size
        self.label = label
        self.font = font or pygame.font.SysFont(None, 20)
        self.checked = checked
        self.callback = callback
        self.hover = False

    def draw(self, surf: pygame.Surface):
        # box
        color = (200, 200, 200) if not self.hover else (220, 220, 220)
        pygame.draw.rect(surf, color, self.rect)
        pygame.draw.rect(surf, (50, 50, 50), self.rect, 2)
        # check mark
        if self.checked:
            # draw a simple X or filled rect
            padding = max(2, self.size // 6)
            inner = self.rect.inflate(-padding * 2, -padding * 2)
            pygame.draw.rect(surf, (30, 144, 255), inner)
        # label
        if self.label:
            lbl = self.font.render(self.label, True, (240, 240, 240))
            surf.blit(lbl, (self.rect.right + 8, self.rect.y + (self.size - lbl.get_height()) // 2))

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.set_checked(not self.checked)

    def set_checked(self, value: bool, call_callback: bool = True):
        if self.checked != value:
            self.checked = value
            if self.callback and call_callback:
                self.callback(self.checked)

# -------------------------
# Slider (水平)
# -------------------------
class Slider:
    def __init__(
        self,
        x: int,
        y: int,
        width: int = 200,
        height: int = 8,
        min_value: float = 0.0,
        max_value: float = 1.0,
        value: float = 0.5,
        step: Optional[float] = None,
        callback: Optional[Callable[[float], None]] = None,
        handle_radius: int = 10,
        font: Optional[pygame.font.Font] = None,
        label: str = "",
    ):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.min = min_value
        self.max = max_value
        self.value = max(min(value, self.max), self.min)
        self.step = step
        self.callback = callback
        self.handle_radius = handle_radius
        self.dragging = False
        self.font = font or pygame.font.SysFont(None, 18)
        self.label = label

        self.track_rect = pygame.Rect(x, y - height // 2, width, height)

    def _value_to_pos(self, val: float) -> int:
        t = (val - self.min) / (self.max - self.min) if self.max != self.min else 0
        return int(self.x + t * self.width)

    def _pos_to_value(self, pos_x: int) -> float:
        t = (pos_x - self.x) / self.width
        t = max(0.0, min(1.0, t))
        val = self.min + t * (self.max - self.min)
        if self.step:
            steps = round((val - self.min) / self.step)
            val = self.min + steps * self.step
        return max(self.min, min(self.max, val))

    def draw(self, surf: pygame.Surface):
        # track
        pygame.draw.rect(surf, (120, 120, 120), self.track_rect, border_radius=self.height//2)
        # filled part
        pos = self._value_to_pos(self.value)
        filled_rect = pygame.Rect(self.x, self.track_rect.y, pos - self.x, self.height)
        pygame.draw.rect(surf, (30, 144, 255), filled_rect, border_radius=self.height//2)
        # handle
        handle_center = (pos, self.y)
        pygame.draw.circle(surf, (255, 255, 255), handle_center, self.handle_radius)
        pygame.draw.circle(surf, (80, 80, 80), handle_center, self.handle_radius, 2)
        # label and value
        if self.label:
            lbl = self.font.render(f"{self.label}: {self.value:.2f}", True, (240, 240, 240))
            surf.blit(lbl, (self.x, self.y - self.handle_radius - 24))

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            pos = self._value_to_pos(self.value)
            handle_rect = pygame.Rect(pos - self.handle_radius, self.y - self.handle_radius,
                                      self.handle_radius * 2, self.handle_radius * 2)
            if handle_rect.collidepoint((mx, my)) or self.track_rect.collidepoint((mx, my)):
                self.dragging = True
                self.set_value(self._pos_to_value(mx))
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging:
                mx = event.pos[0]
                self.set_value(self._pos_to_value(mx))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging:
                self.dragging = False

    def set_value(self, val: float, call_callback: bool = True):
        val = max(self.min, min(self.max, val))
        if self.step:
            steps = round((val - self.min) / self.step)
            val = self.min + steps * self.step
        if abs(val - self.value) > 1e-6:
            self.value = val
            if self.callback and call_callback:
                self.callback(self.value)

# -------------------------
# Demo main（可直接執行檔案觀看效果）
# -------------------------
if __name__ == "__main__":
    WIDTH, HEIGHT = 640, 360
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    pygame.display.set_caption("Checkbox & Slider Demo")

    font = pygame.font.SysFont(None, 20)

    # 回呼函式示範
    def on_checkbox_changed(val):
        print("Checkbox:", val)

    def on_slider_changed(val):
        print("Slider value:", val)

    cb = Checkbox(20, 20, size=24, label="Enable Feature", font=font, checked=False, callback=on_checkbox_changed)
    slider = Slider(20, 80, width=300, min_value=0.0, max_value=100.0, value=25.0, step=1.0,
                    callback=on_slider_changed, label="Volume", font=font)

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            cb.handle_event(ev)
            slider.handle_event(ev)

        screen.fill((30, 30, 30))
        cb.draw(screen)
        slider.draw(screen)

        # 顯示目前值（整合示範）
        status = font.render(f"Checkbox = {cb.checked}    Slider = {slider.value:.0f}", True, (200, 200, 200))
        screen.blit(status, (20, 140))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()