import pygame as pg
from src.utils import GameSettings
from src.interface.components import Button


class ShopOverlay:
    """Shop overlay for buying and selling items"""
    
    def __init__(self, game_manager):
        self.game_manager = game_manager
        self.active = False
        self.mode = "buy"  # "buy" or "sell"
        self.info_message: str = ""
        self.info_timer: float = 0.0
        
        # Shop inventory - items available for purchase
        self.shop_items = [
            {"name": "Rare Candy", "price": 50, "sprite_path": "ingame_ui/potion.png"},
            {"name": "Pokeball", "price": 10, "sprite_path": "ingame_ui/ball.png"},
            {"name": "Heal Potion", "price": 20, "sprite_path": "ingame_ui/potion.png"},
            {"name": "Strength Potion", "price": 20, "sprite_path": "ingame_ui/potion.png"},
            {"name": "Defense Potion", "price": 20, "sprite_path": "ingame_ui/potion.png"},
        ]
        # Scroll position
        self.scroll_offset = 0
        self.max_scroll = 0
        
        # UI dimensions
        self.panel_width = 600
        self.panel_height = 500
        self.panel_x = (GameSettings.SCREEN_WIDTH - self.panel_width) // 2
        self.panel_y = (GameSettings.SCREEN_HEIGHT - self.panel_height) // 2
        
        # Colors
        self.bg_color = (40, 40, 60, 230)
        self.title_color = (0, 0, 0)  # Black
        self.text_color = (0, 0, 0)  # Black
        self.button_color = (60, 60, 80)
        self.button_hover_color = (80, 80, 100)
        self.selected_color = (100, 150, 200, 100)
        
        # Selected item index
        self.selected_index = -1
        
        # Individual sell buttons for each Pokemon
        self.buy_buttons = []
        self.sell_buttons = []
        
        # Create buttons
        btn_y = self.panel_y + 60
        self.buy_button = Button(
            "UI/raw/UI_Flat_Bar01a.png", "UI/raw/UI_Flat_Bar01a.png",
            self.panel_x + 50, btn_y, 100, 40,
            self._switch_to_buy
        )
        self.sell_button = Button(
            "UI/raw/UI_Flat_Bar01a.png", "UI/raw/UI_Flat_Bar01a.png",
            self.panel_x + 170, btn_y, 100, 40,
            self._switch_to_sell
        )
        self.close_button = Button(
            "UI/button_x.png", "UI/button_x_hover.png",
            self.panel_x + self.panel_width - 60, self.panel_y + 10, 50, 50,
            self.close
        )

        # Initialize per-item buttons
        self._create_buy_buttons()
    
    def _switch_to_buy(self):
        self.mode = "buy"
        self.selected_index = -1
        self.scroll_offset = 0
        self._create_buy_buttons()
    
    def _switch_to_sell(self):
        self.mode = "sell"
        self.selected_index = -1
        self.scroll_offset = 0
        self._create_sell_buttons()

    def _set_info(self, msg: str, duration: float = 2.0):
        """Show a short info message on the shop panel."""
        self.info_message = msg
        self.info_timer = duration

    def _create_buy_buttons(self):
        """Create individual buy buttons for each shop item"""
        self.buy_buttons = []
        list_x = self.panel_x + 20
        list_y = self.panel_y + 120
        list_width = self.panel_width - 40
        item_height = 60

        for i, item in enumerate(self.shop_items):
            btn_x = list_x + list_width - 65
            btn_y = list_y + i * item_height + 10

            buy_func = lambda idx=i: self._buy_item(idx)
            btn = Button(
                "UI/button_shop.png", "UI/button_shop_hover.png",
                btn_x, btn_y, 50, 40,
                buy_func
            )
            self.buy_buttons.append(btn)
    
    def _create_sell_buttons(self):
        """Create individual sell buttons for each Pokemon"""
        self.sell_buttons = []
        monsters = self.game_manager.bag._monsters_data if hasattr(self.game_manager.bag, '_monsters_data') else []
        
        list_x = self.panel_x + 20
        list_y = self.panel_y + 120
        list_width = self.panel_width - 40
        item_height = 80
        
        for i in range(len(monsters)):
            btn_x = list_x + list_width - 65
            btn_y = list_y + i * item_height + 20
            
            # Create a lambda with default parameter to capture current index
            sell_func = lambda idx=i: self._sell_pokemon(idx)
            
            btn = Button(
                "UI/button_shop.png", "UI/button_shop_hover.png",
                btn_x, btn_y, 50, 40,
                sell_func
            )
            self.sell_buttons.append(btn)

    def _buy_item(self, index):
        """Buy a specific item"""
        if 0 <= index < len(self.shop_items):
            self.selected_index = index
            self._perform_transaction()
    
    def _sell_pokemon(self, index):
        """Sell a specific Pokemon"""
        monsters = self.game_manager.bag._monsters_data if hasattr(self.game_manager.bag, '_monsters_data') else []
        
        if 0 <= index < len(monsters):
            # Prevent selling the last remaining Pokemon
            if len(monsters) <= 1:
                self._set_info("you have to obtain at least 1 pokemon")
                return
            # Remove Pokemon from bag
            monsters.pop(index)
            # Add coins
            self._add_coins(50)
            # Recreate buttons since list changed
            self._create_sell_buttons()
            # Reset selection and clamp scroll if list shrank
            self.selected_index = -1
            list_height = self.panel_height - 200
            item_height = 80
            max_scroll = max(0, len(monsters) * item_height - list_height)
            if self.scroll_offset > max_scroll:
                self.scroll_offset = max_scroll
    
    def open(self):
        """Open the shop overlay"""
        self.active = True
        self.mode = "buy"
        self.selected_index = -1
        self.scroll_offset = 0
    
    def close(self):
        """Close the shop overlay"""
        self.active = False
        self.selected_index = -1
    
    def _get_player_coins(self) -> int:
        """Get the number of coins the player has"""
        for item in self.game_manager.bag._items_data:
            if item.get("name") == "Coins":
                return item.get("count", 0)
        return 0
    
    def _add_coins(self, amount: int):
        """Add coins to player's inventory"""
        for item in self.game_manager.bag._items_data:
            if item.get("name") == "Coins":
                item["count"] = item.get("count", 0) + amount
                return
        # If no coins item exists, create it
        self.game_manager.bag._items_data.append({
            "name": "Coins",
            "count": amount,
            "sprite_path": "ingame_ui/coin.png"
        })
    
    def _remove_coins(self, amount: int) -> bool:
        """Remove coins from player's inventory. Returns True if successful."""
        for item in self.game_manager.bag._items_data:
            if item.get("name") == "Coins":
                current = item.get("count", 0)
                if current >= amount:
                    item["count"] = current - amount
                    return True
        return False
    
    def _perform_transaction(self):
        """Buy or sell the selected item"""
        if self.selected_index < 0:
            return
        
        if self.mode == "buy":
            if self.selected_index >= len(self.shop_items):
                return
            
            item = self.shop_items[self.selected_index]
            price = item["price"]
            
            # Check if player has enough coins
            if self._get_player_coins() >= price:
                # Deduct coins
                if self._remove_coins(price):
                    # Add item to player's inventory
                    found = False
                    for player_item in self.game_manager.bag._items_data:
                        if player_item.get("name") == item["name"]:
                            player_item["count"] = player_item.get("count", 0) + 1
                            found = True
                            break
                    
                    if not found:
                        # Add new item
                        self.game_manager.bag._items_data.append({
                            "name": item["name"],
                            "count": 1,
                            "sprite_path": item["sprite_path"]
                        })
        
        elif self.mode == "sell":
            # In sell mode, we're selling Pokemon, not items
            monsters = self.game_manager.bag._monsters_data if hasattr(self.game_manager.bag, '_monsters_data') else []
            
            if self.selected_index >= len(monsters):
                return
            
            monster = monsters[self.selected_index]
            if monster:
                # Sell for coins (fixed price per monster)
                sell_price = 50  # Default sell price for Pokemon
                
                # Prevent selling the last remaining Pokemon
                if len(monsters) <= 1:
                    self._set_info("you have to obtain at least 1 pokemon")
                    return
                # Remove Pokemon from bag (this is a simplified sell - just remove it)
                if self.selected_index < len(monsters):
                    monsters.pop(self.selected_index)
                    self._add_coins(sell_price)
                    self.selected_index = -1
                    # Clamp scroll after removal to keep list in sync
                    list_height = self.panel_height - 200
                    item_height = 80
                    max_scroll = max(0, len(monsters) * item_height - list_height)
                    if self.scroll_offset > max_scroll:
                        self.scroll_offset = max_scroll
    
    def handle_event(self, event: pg.event.Event):
        """Handle mouse and keyboard events"""
        if not self.active:
            return
        
        # Button events
        self.buy_button.handle_event(event)
        self.sell_button.handle_event(event)
        self.close_button.handle_event(event)

        # Handle buy button events in buy mode
        if self.mode == "buy":
            for btn in self.buy_buttons:
                btn.handle_event(event)
        
        # Handle sell button events in sell mode
        if self.mode == "sell":
            for btn in self.sell_buttons:
                btn.handle_event(event)
        
        # Mouse click to select items
        if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            
            # Check if click is within item list area
            list_x = self.panel_x + 20
            list_y = self.panel_y + 120
            list_width = self.panel_width - 40
            item_height = 60 if self.mode == "buy" else 80
            
            if self.mode == "buy":
                items = self.shop_items
            else:
                items = self.game_manager.bag._monsters_data if hasattr(self.game_manager.bag, '_monsters_data') else []
            
            for i, item in enumerate(items):
                item_y = list_y + i * item_height - self.scroll_offset
                if (list_x <= mx <= list_x + list_width and 
                    item_y <= my <= item_y + item_height and
                    item_y >= list_y and item_y + item_height <= self.panel_y + self.panel_height - 80):
                    self.selected_index = i
                    break
        
        # Scroll with mouse wheel (supports both MOUSEWHEEL and legacy buttons 4/5)
        wheel_delta = 0
        if event.type == pg.MOUSEWHEEL:
            wheel_delta = event.y
        elif event.type == pg.MOUSEBUTTONDOWN and event.button in (4, 5):
            wheel_delta = 1 if event.button == 4 else -1
        if wheel_delta != 0 and self.mode == "sell":
            # Only scroll when hovering over the Pokémon list area in SELL mode
            mx, my = pg.mouse.get_pos()
            list_x = self.panel_x + 20
            list_y = self.panel_y + 120
            list_width = self.panel_width - 40
            list_height = self.panel_height - 200
            if (list_x <= mx <= list_x + list_width and list_y <= my <= list_y + list_height):
                item_height = 80
                monsters = self.game_manager.bag._monsters_data if hasattr(self.game_manager.bag, '_monsters_data') else []
                max_scroll = max(0, len(monsters) * item_height - list_height)
                self.scroll_offset = max(0, min(max_scroll, self.scroll_offset - wheel_delta * 30))
    
    def update(self, dt: float):
        """Update overlay state"""
        if not self.active:
            return

        if self.info_timer > 0:
            self.info_timer -= dt
            if self.info_timer <= 0:
                self.info_message = ""
        
        # Update buttons
        self.buy_button.update(dt)
        self.sell_button.update(dt)
        self.close_button.update(dt)

        # Update buy buttons with scroll offset
        if self.mode == "buy":
            list_y = self.panel_y + 120
            item_height = 60
            for i, btn in enumerate(self.buy_buttons):
                btn.hitbox.y = list_y + i * item_height + 10 - self.scroll_offset
                btn.update(dt)
        
        # Update sell buttons with scroll offset
        if self.mode == "sell":
            list_y = self.panel_y + 120
            item_height = 80
            
            for i, btn in enumerate(self.sell_buttons):
                btn.hitbox.y = list_y + i * item_height + 20 - self.scroll_offset
                btn.update(dt)
        
        # Calculate max scroll
        if self.mode == "buy":
            items = self.shop_items
            item_height = 60
        else:
            items = self.game_manager.bag._monsters_data if hasattr(self.game_manager.bag, '_monsters_data') else []
            item_height = 80  # Larger for Pokemon
        
        list_height = self.panel_height - 200
        self.max_scroll = max(0, len(items) * item_height - list_height)
    
    def draw(self, screen: pg.Surface):
        """Draw the shop overlay"""
        if not self.active:
            return
        
        # Draw semi-transparent background
        overlay_surf = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
        overlay_surf.fill((0, 0, 0, 150))
        screen.blit(overlay_surf, (0, 0))
        
        # Draw main panel using UI_Flat_Frame03a
        from src.core.services import resource_manager
        try:
            bg_img = resource_manager.get_image("UI/raw/UI_Flat_Frame03a.png")
            bg_img = pg.transform.scale(bg_img, (self.panel_width, self.panel_height))
            screen.blit(bg_img, (self.panel_x, self.panel_y))
        except Exception:
            # Fallback to solid color if image fails to load
            panel_surf = pg.Surface((self.panel_width, self.panel_height), pg.SRCALPHA)
            panel_surf.fill(self.bg_color)
            pg.draw.rect(panel_surf, (80, 80, 120), panel_surf.get_rect(), 3)
            screen.blit(panel_surf, (self.panel_x, self.panel_y))
        
        # Draw title
        font_title = pg.font.Font(None, 48)
        title_text = font_title.render("SHOP", True, (0, 0, 0))  # Black
        screen.blit(title_text, (self.panel_x + 20, self.panel_y + 10))
        
        # Draw player's coins
        font_small = pg.font.Font(None, 32)
        coins_text = font_small.render(f"Coins: {self._get_player_coins()}", True, (0, 0, 0))  # Black
        # Shift left a bit to align better with buttons
        screen.blit(coins_text, (self.panel_x + self.panel_width - 190, self.panel_y + 20))
        
        # Draw mode buttons with background
        try:
            bar_img = resource_manager.get_image("UI/raw/UI_Flat_Bar01a.png")
            
            # Draw BUY button background
            buy_bar = pg.transform.scale(bar_img, (100, 40))
            screen.blit(buy_bar, (self.panel_x + 50, self.panel_y + 60))
            
            # Draw SELL button background
            sell_bar = pg.transform.scale(bar_img, (100, 40))
            screen.blit(sell_bar, (self.panel_x + 170, self.panel_y + 60))
        except Exception:
            pass
        
        self.buy_button.draw(screen)
        self.sell_button.draw(screen)
        
        # Draw mode labels on buttons
        font_btn = pg.font.Font(None, 28)
        buy_label = font_btn.render("BUY", True, (0, 0, 0))  # Black
        sell_label = font_btn.render("SELL", True, (0, 0, 0))  # Black
        screen.blit(buy_label, (self.panel_x + 78, self.panel_y + 70))
        screen.blit(sell_label, (self.panel_x + 195, self.panel_y + 70))

        # Info message
        if self.info_message:
            info_font = pg.font.Font(None, 26)
            info_surf = info_font.render(self.info_message, True, (200, 50, 50))
            screen.blit(info_surf, (self.panel_x + 50, self.panel_y + 100))
        
        # Draw item list
        self._draw_item_list(screen)

        # Draw buy buttons in buy mode
        if self.mode == "buy":
            list_y = self.panel_y + 120
            list_height = self.panel_height - 200
            for btn in self.buy_buttons:
                if btn.hitbox.y >= list_y and btn.hitbox.y + btn.hitbox.height <= list_y + list_height:
                    btn.draw(screen)
        
        # Draw sell buttons in sell mode
        if self.mode == "sell":
            list_y = self.panel_y + 120
            list_height = self.panel_height - 200
            for btn in self.sell_buttons:
                # Only draw buttons that are within the visible area
                if btn.hitbox.y >= list_y and btn.hitbox.y + btn.hitbox.height <= list_y + list_height:
                    btn.draw(screen)
        
        # Draw close button
        self.close_button.draw(screen)
    
    def _draw_item_list(self, screen: pg.Surface):
        """Draw the list of items (shop items or pokemon)"""
        font = pg.font.Font(None, 24)
        font_small = pg.font.Font(None, 20)
        
        list_x = self.panel_x + 20
        list_y = self.panel_y + 120
        list_width = self.panel_width - 40
        list_height = self.panel_height - 200
        
        # Different item height based on mode
        if self.mode == "buy":
            item_height = 60
        else:
            item_height = 80
        
        # Create clipping rect
        clip_rect = pg.Rect(list_x, list_y, list_width, list_height)
        screen.set_clip(clip_rect)
        
        # Get items to display
        if self.mode == "buy":
            items = self.shop_items
        else:
            items = self.game_manager.bag._monsters_data if hasattr(self.game_manager.bag, '_monsters_data') else []
        
        # Load banner image for item backgrounds
        from src.core.services import resource_manager
        try:
            banner_img = resource_manager.get_image("UI/raw/UI_Flat_Banner03a.png")
        except Exception:
            banner_img = None
        
        # Draw each item
        for i, item in enumerate(items):
            item_y = list_y + i * item_height - self.scroll_offset
            
            # Skip if outside visible area
            if item_y + item_height < list_y or item_y > list_y + list_height:
                continue
            
            # Draw selection highlight
            if i == self.selected_index:
                highlight_surf = pg.Surface((list_width - 10, item_height - 5), pg.SRCALPHA)
                highlight_surf.fill(self.selected_color)
                screen.blit(highlight_surf, (list_x + 5, item_y + 2))
            
            # Draw item background using banner image
            item_rect = pg.Rect(list_x + 5, item_y + 2, list_width - 10, item_height - 5)
            if banner_img:
                try:
                    scaled_banner = pg.transform.scale(banner_img, (item_rect.width, item_rect.height))
                    screen.blit(scaled_banner, (item_rect.x, item_rect.y))
                except Exception:
                    # Fallback to solid color
                    pg.draw.rect(screen, (50, 50, 70), item_rect)
                    pg.draw.rect(screen, (100, 100, 120), item_rect, 2)
            else:
                # Fallback to solid color
                pg.draw.rect(screen, (50, 50, 70), item_rect)
                pg.draw.rect(screen, (100, 100, 120), item_rect, 2)
            
            # Draw item/Pokemon content
            if self.mode == "buy":
                # Thumbnail
                if item.get("sprite_path"):
                    try:
                        sprite_img = resource_manager.get_image(item["sprite_path"])
                        sprite_img = pg.transform.scale(sprite_img, (40, 40))
                        screen.blit(sprite_img, (list_x + 35, item_y + 7))
                    except Exception:
                        pass

                # Draw item name
                name_text = font.render(item["name"], True, (0, 0, 0))  # Black text
                if name_text.get_width() > list_width - 160:
                    name_text = font.render(item["name"][:12] + "...", True, (0, 0, 0))
                screen.blit(name_text, (list_x + 90, item_y + 10))

                # Quantity label
                qty_text = font_small.render("x1", True, (0, 0, 0))
                screen.blit(qty_text, (list_x + list_width - 175, item_y + 20))

                # Price text near the button
                price_text = font_small.render(f"${item['price']}", True, (0, 0, 0))
                screen.blit(price_text, (list_x + list_width - 90, item_y + 20))
            else:
                # Draw Pokemon info
                # Pokemon name
                name_text = font.render(item.get("name", "Unknown"), True, (0, 0, 0))
                screen.blit(name_text, (list_x + 70, item_y + 5))
                
                # Level
                level = item.get("level", "?")
                level_text = font_small.render(f"Lv. {level}", True, (0, 0, 0))
                # Shift left so it doesn't overlap the button
                screen.blit(level_text, (list_x + list_width - 140, item_y + 5))
                
                # HP display
                hp = item.get("hp", 0)
                max_hp = item.get("max_hp", 1)
                hp_text = font_small.render(f"HP: {hp}/{max_hp}", True, (0, 0, 0))
                screen.blit(hp_text, (list_x + 70, item_y + 30))
                
                # Sell price
                sell_price = 50
                sell_text = font_small.render(f"Price: {sell_price}", True, (0, 0, 0))
                # Shift left so it doesn't overlap the button
                screen.blit(sell_text, (list_x + list_width - 140, item_y + 30))
                
                # Draw Pokemon thumbnail if available
                if item.get("sprite_path"):
                    try:
                        sprite_img = resource_manager.get_image(item["sprite_path"])
                        sprite_img = pg.transform.scale(sprite_img, (50, 50))
                        screen.blit(sprite_img, (list_x + 15, item_y + 15))
                    except Exception:
                        pass
        
        # Reset clip
        screen.set_clip(None)
