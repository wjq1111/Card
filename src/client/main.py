from __future__ import annotations

import ctypes
import json
import os
import random
import time
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path

import pygame

from src.client.network import PokerClientConnection
from src.proto_gen import poker_pb2
from src.shared.game_logging import GameLogStore


WIDTH = 1280
HEIGHT = 780
FPS = 60
SIDE_PANEL_WIDTH = 252
LAYOUT_GAP = 26
MIN_TABLE_WIDTH = 430
MIN_TABLE_HEIGHT = 280

BG = (13, 20, 24)
PANEL = (25, 35, 39)
PANEL_2 = (32, 45, 49)
FELT = (29, 103, 74)
FELT_DARK = (20, 74, 55)
GOLD = (235, 190, 82)
RED = (202, 70, 76)
BLUE = (91, 151, 230)
GREEN = (61, 157, 109)
TEXT = (238, 245, 241)
MUTED = (176, 192, 187)
LINE = (54, 74, 78)
CARD = (247, 242, 226)
CARD_RED = (184, 43, 58)
CARD_BLACK = (30, 36, 39)

AVATAR_THEMES = {
    "ember": {"bg": (137, 58, 42), "fg": (255, 223, 183), "accent": (247, 166, 93)},
    "mint": {"bg": (49, 121, 109), "fg": (220, 245, 234), "accent": (132, 223, 188)},
    "ocean": {"bg": (48, 82, 132), "fg": (226, 238, 255), "accent": (130, 180, 255)},
    "violet": {"bg": (96, 71, 134), "fg": (237, 228, 255), "accent": (183, 150, 246)},
    "sun": {"bg": (154, 113, 42), "fg": (255, 239, 201), "accent": (255, 211, 92)},
    "rose": {"bg": (142, 61, 92), "fg": (255, 228, 238), "accent": (244, 154, 191)},
}
DEFAULT_AVATAR_IDS = list(AVATAR_THEMES.keys())
UI_CONFIG_PATH = Path(__file__).resolve().parents[2] / "assets" / "ui" / "login_layout.json"


def default_login_ui_config() -> dict[str, object]:
    return {
        "login": {
            "breakpoint_wide": 980,
            "shell": {
                "margin_x": 36,
                "margin_y": 52,
                "min_width": 920,
                "max_height": 620,
            },
            "wide": {
                "showcase_inset": 28,
                "panel_gap": 22,
                "showcase_width_ratio": 0.42,
            },
            "narrow": {
                "panel_inset": 24,
                "panel_gap": 18,
                "showcase_height": 190,
            },
            "form": {
                "padding_x": 34,
                "address_y": 148,
                "name_y": 236,
                "input_height": 48,
                "button_height": 48,
                "button_bottom_offset": 70,
            },
            "avatar_card": {
                "top_gap": 24,
                "bottom_gap": 20,
                "min_height_closed": 128,
                "min_height_open": 220,
                "preview_size": 96,
                "preview_left": 18,
                "preview_vertical_margin": 20,
                "grid_top": 56,
                "grid_bottom": 12,
                "grid_padding_x": 12,
            },
        }
    }


def merge_login_ui_config(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_login_ui_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def enable_high_dpi() -> None:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    action: str
    color: tuple[int, int, int] = PANEL_2
    enabled: bool = True

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        mouse = pygame.mouse.get_pos()
        base = self.color if self.enabled else (43, 50, 52)
        if self.enabled and self.rect.collidepoint(mouse):
            base = tuple(min(255, channel + 18) for channel in base)
        pygame.draw.rect(surface, base, self.rect, border_radius=10)
        pygame.draw.rect(surface, LINE, self.rect, width=1, border_radius=10)
        draw_centered(surface, font, self.label, self.rect, TEXT if self.enabled else MUTED)

    def hit(self, event: pygame.event.Event) -> bool:
        return (
            self.enabled
            and event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        )


class TextInput:
    def __init__(self, rect: pygame.Rect, value: str) -> None:
        self.rect = rect
        self.value = value
        self.active = False

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)
        elif self.active and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_TAB):
                self.active = False
            elif event.unicode and len(self.value) < 32:
                self.value += event.unicode

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, label: str) -> None:
        draw_text(surface, font, label, self.rect.x, self.rect.y - 28, MUTED)
        border = GOLD if self.active else LINE
        pygame.draw.rect(surface, (18, 27, 31), self.rect, border_radius=10)
        pygame.draw.rect(surface, border, self.rect, width=1, border_radius=10)
        draw_text_clipped(surface, font, self.value, self.rect.x + 14, self.rect.y + 11, self.rect.width - 28, TEXT)


class PokerApp:
    def __init__(self, ui_debug: bool = False) -> None:
        enable_high_dpi()
        pygame.init()
        pygame.display.set_caption("Texas Holdem Online")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Microsoft YaHei UI", 22)
        self.small = pygame.font.SysFont("Microsoft YaHei UI", 18)
        self.title_font = pygame.font.SysFont("Microsoft YaHei UI", 36, bold=True)
        self.card_font = pygame.font.SysFont("Arial", 26, bold=True)

        self.address_input = TextInput(
            pygame.Rect(430, 256, 420, 48),
            os.getenv("POKER_SERVER", "119.45.157.13:50051"),
        )
        self.name_input = TextInput(pygame.Rect(430, 346, 420, 48), f"Player{random.randint(100, 999)}")
        self.connection: PokerClientConnection | None = None
        self.player_name = ""
        self.selected_avatar_id = DEFAULT_AVATAR_IDS[0]
        self.ui_state = "LOGIN"
        self.lobby_snapshot = poker_pb2.LobbySnapshot()
        self.snapshot = None
        self.selected_room_id = ""
        self.status = "请输入用户名后进入大厅。"
        self.last_heartbeat = time.monotonic()
        self.running = True
        self.log_store = GameLogStore("runtime_logs", "client", "anonymous")
        self._last_state_key: tuple[object, ...] | None = None
        self._login_avatar_hitboxes: list[tuple[pygame.Rect, str]] = []
        self._room_hitboxes: list[tuple[pygame.Rect, str]] = []
        self._avatar_picker_open = False
        self.ui_debug = ui_debug
        self.ui_config = default_login_ui_config()
        self._ui_config_mtime: float | None = None
        self._last_ui_config_check = 0.0
        self._load_ui_config(force=True)

    def run(self) -> None:
        while self.running:
            self.refresh_ui_config()
            buttons = self.make_buttons()
            for event in pygame.event.get():
                self.handle_event(event, buttons)

            self.update_network()
            self.draw(buttons)
            pygame.display.flip()
            self.clock.tick(FPS)
        pygame.quit()

    def handle_event(self, event: pygame.event.Event, buttons: list[Button]) -> None:
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F1:
            self.ui_debug = not self.ui_debug
            self.status = f"UI 调试模式{'开启' if self.ui_debug else '关闭'}"
            return
        if self.ui_debug and event.type == pygame.KEYDOWN and event.key == pygame.K_F5:
            self._load_ui_config(force=True)
            return

        if self.ui_state == "LOGIN":
            self.handle_login_event(event)
        elif self.ui_state == "LOBBY":
            self.handle_lobby_event(event)

        for button in buttons:
            if button.hit(event):
                self.dispatch(button.action)

    def handle_lobby_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        for rect, room_id in self._room_hitboxes:
            if rect.collidepoint(event.pos):
                self.selected_room_id = room_id
                return

    def handle_login_event(self, event: pygame.event.Event) -> None:
        self.address_input.handle(event)
        self.name_input.handle(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            layout = self.login_layout()
            if self._avatar_picker_open:
                for rect, avatar_id in self.login_avatar_hitboxes():
                    if rect.collidepoint(event.pos):
                        self.selected_avatar_id = avatar_id
                        self._avatar_picker_open = False
                        return
                if not layout["avatars_area"].collidepoint(event.pos):
                    self._avatar_picker_open = False
                    return
            elif layout["preview"].collidepoint(event.pos):
                self._avatar_picker_open = True
                return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            self.dispatch("login")

    def dispatch(self, action: str) -> None:
        if action == "login":
            self.login()
        elif action == "refresh":
            self.send(poker_pb2.ClientEvent(list_rooms=poker_pb2.ListRooms()))
        elif action == "create_room":
            self.send(poker_pb2.ClientEvent(create_room=poker_pb2.CreateRoom()))
        elif action == "join_room" and self.selected_room_id:
            self.send(
                poker_pb2.ClientEvent(join_room_by_id=poker_pb2.JoinRoomById(room_id=self.selected_room_id))
            )
        elif action == "leave_room":
            self.send(poker_pb2.ClientEvent(leave_room=poker_pb2.LeaveRoom()))
            self.snapshot = None
        elif action.startswith("seat:"):
            seat_index = int(action.split(":")[1])
            hero_seat = self.hero_seat()
            if hero_seat:
                self.send(poker_pb2.ClientEvent(change_seat=poker_pb2.ChangeSeat(seat_index=seat_index)))
            else:
                self.send(poker_pb2.ClientEvent(sit_down=poker_pb2.SitDown(seat_index=seat_index)))
        elif action == "stand":
            self.send(poker_pb2.ClientEvent(stand_up=poker_pb2.StandUp()))
        elif action == "ready":
            hero_seat = self.hero_seat()
            if hero_seat:
                self.send(poker_pb2.ClientEvent(set_ready=poker_pb2.SetReady(ready=not hero_seat.ready)))
        elif action == "start_game":
            self.send(poker_pb2.ClientEvent(start_hand=poker_pb2.StartHand()))
        elif action == "add_bot":
            self.send(poker_pb2.ClientEvent(chat_message=poker_pb2.ChatMessage(text="/addbot")))
            self.status = "已请求添加 guarded bot。"
        elif action == "fold":
            self.move(poker_pb2.FOLD)
        elif action == "check":
            self.move(poker_pb2.CHECK)
        elif action == "call":
            self.move(poker_pb2.CALL)
        elif action == "raise":
            amount = self.snapshot.current_bet + self.snapshot.min_raise if self.snapshot else 0
            self.move(poker_pb2.RAISE, amount)
        elif action == "all_in":
            self.move(poker_pb2.ALL_IN)

    def login(self) -> None:
        name = self.name_input.value.strip()
        if not name:
            self.status = "用户名不能为空。"
            return
        address = self.address_input.value.strip() or "119.45.157.13:50051"
        self.player_name = name
        self.connection = PokerClientConnection(address)
        self.connection.send(
            poker_pb2.ClientEvent(login=poker_pb2.Login(name=name, avatar_id=self.selected_avatar_id))
        )
        self.status = f"正在连接 {address}..."

    def move(self, move_type: int, amount: int = 0) -> None:
        self.send(poker_pb2.ClientEvent(player_move=poker_pb2.PlayerMove(type=move_type, amount=amount)))

    def send(self, event: poker_pb2.ClientEvent) -> None:
        if not self.connection:
            self.status = "尚未连接服务器。"
            return
        self.connection.send(event)

    def update_network(self) -> None:
        if not self.connection:
            return

        if time.monotonic() - self.last_heartbeat > 5:
            self.send(poker_pb2.ClientEvent(heartbeat=poker_pb2.Heartbeat()))
            self.last_heartbeat = time.monotonic()

        for server_event in self.connection.poll():
            payload = server_event.WhichOneof("payload")
            if payload == "login_accepted":
                self.connection.set_identity(
                    server_event.login_accepted.player_id,
                    server_event.login_accepted.reconnect_token,
                )
                self.log_store = self.log_store.with_owner(server_event.login_accepted.player_id)
                self.player_name = server_event.login_accepted.player_name
                self.selected_avatar_id = server_event.login_accepted.avatar_id or self.selected_avatar_id
                self.status = f"欢迎回来，{self.player_name}。"
            elif payload == "lobby_snapshot":
                self.lobby_snapshot = server_event.lobby_snapshot
                self.ui_state = "LOBBY"
                self.snapshot = None
                if self.selected_room_id and not any(
                    room.room_id == self.selected_room_id for room in self.lobby_snapshot.rooms
                ):
                    self.selected_room_id = ""
                self.status = f"大厅房间数：{len(self.lobby_snapshot.rooms)}"
            elif payload == "joined":
                self.status = f"已进入房间 {server_event.joined.room_id}"
            elif payload == "snapshot":
                self.snapshot = server_event.snapshot
                self.ui_state = "ROOM"
                self.log_snapshot(server_event.snapshot)
            elif payload == "error":
                prefix = f"{server_event.error.code}: " if server_event.error.code else ""
                self.status = prefix + server_event.error.message
            elif payload == "server_notice":
                if server_event.server_notice.message != "heartbeat_ack":
                    self.status = server_event.server_notice.message

    def log_snapshot(self, snapshot) -> None:
        state_key = (
            snapshot.current_hand_id,
            snapshot.phase,
            snapshot.pot,
            snapshot.active_seat,
            snapshot.starting_countdown_seconds,
            snapshot.hand_number,
            snapshot.room_status,
        )
        if state_key != self._last_state_key:
            self._last_state_key = state_key
            self.log_store.write(
                snapshot.room_id,
                "Snapshot updated",
                phase=poker_pb2.GamePhase.Name(snapshot.phase),
                event_type="SNAPSHOT",
                hand_id=snapshot.current_hand_id,
                hand_number=snapshot.hand_number,
                data={
                    "room_status": poker_pb2.RoomStatus.Name(snapshot.room_status),
                    "pot": snapshot.pot,
                    "active_seat": snapshot.active_seat,
                    "countdown": snapshot.starting_countdown_seconds,
                },
            )

    def make_buttons(self) -> list[Button]:
        if self.ui_state == "LOGIN":
            layout = self.login_layout()
            return [Button(layout["button"], "进入大厅", "login", GREEN)]
        if self.ui_state == "LOBBY":
            return self.make_lobby_buttons()
        return self.make_room_buttons()

    def make_lobby_buttons(self) -> list[Button]:
        width, _ = self.screen.get_size()
        has_selection = bool(self.selected_room_id)
        specs = [
            ("刷新", "refresh", PANEL_2, self.connection is not None),
            ("创建房间", "create_room", GREEN, self.connection is not None),
            ("加入房间", "join_room", BLUE, has_selection),
        ]
        rects = layout_button_row(width - 44, 42, 112, 42, len(specs), gap=12)
        return [Button(rect, label, action, color, enabled) for rect, (label, action, color, enabled) in zip(rects, specs)]

    def make_room_buttons(self) -> list[Button]:
        width, height = self.screen.get_size()
        layout = self.room_layout(width, height)
        header_specs: list[tuple[str, str, tuple[int, int, int], bool]] = [
            ("离开房间", "leave_room", PANEL_2, True),
        ]
        hero_seat = self.hero_seat()
        can_toggle_ready = bool(
            hero_seat
            and self.snapshot
            and self.snapshot.room_status == poker_pb2.OPEN
            and self.snapshot.phase in (poker_pb2.WAITING, poker_pb2.HAND_COMPLETE)
        )
        ready_label = "取消准备" if hero_seat and hero_seat.ready else "准备"
        if hero_seat:
            header_specs.insert(0, (ready_label, "ready", GOLD, can_toggle_ready))
            header_specs.insert(
                1,
                (
                    "离座",
                    "stand",
                    PANEL_2,
                    bool(self.snapshot and self.snapshot.room_status == poker_pb2.OPEN),
                ),
            )
        if self.is_room_owner():
            header_specs.insert(0, ("添加 Bot", "add_bot", BLUE, self.can_add_bot()))
            header_specs.insert(0, ("开始游戏", "start_game", GREEN, self.can_start_game()))

        header_rects = layout_button_row(width - 44, 42, 106, 42, len(header_specs), gap=8)
        buttons = [
            Button(rect, label, action, color, enabled)
            for rect, (label, action, color, enabled) in zip(header_rects, header_specs)
        ]

        seat_button_width = 82 if width >= 1100 else 74
        seat_button_gap = 10 if width >= 1100 else 8
        seat_total_width = seat_button_width * 6 + seat_button_gap * 5
        seat_start_x = max(26, min(layout["table"].centerx - seat_total_width // 2, width - seat_total_width - 26))
        for index in range(6):
            occupied = bool(self.snapshot and self.snapshot.seats[index].player_id)
            seat_enabled = bool(
                self.snapshot
                and self.snapshot.room_status == poker_pb2.OPEN
                and not occupied
            )
            buttons.append(
                Button(
                    pygame.Rect(seat_start_x + index * (seat_button_width + seat_button_gap), height - 66, seat_button_width, 40),
                    f"座位 {index + 1}",
                    f"seat:{index}",
                    PANEL_2,
                    seat_enabled,
                )
            )

        actions = self.available_actions()
        specs = [
            ("弃牌", "fold", RED, actions["fold"]),
            ("过牌", "check", PANEL_2, actions["check"]),
            ("跟注", "call", BLUE, actions["call"]),
            ("加注", "raise", GOLD, actions["raise"]),
            ("全下", "all_in", RED, actions["all_in"]),
        ]
        action_rects = layout_button_row(width - 26, height - 66, 90, 40, len(specs), gap=12)
        for rect, (label, action, color, enabled) in zip(action_rects, specs):
            buttons.append(Button(rect, label, action, color, enabled))
        return buttons

    def hero_seat(self):
        if not self.connection or not self.snapshot:
            return None
        return next((seat for seat in self.snapshot.seats if seat.player_id == self.connection.player_id), None)

    def is_room_owner(self) -> bool:
        return bool(self.connection and self.snapshot and self.snapshot.owner_player_id == self.connection.player_id)

    def can_start_game(self) -> bool:
        if not self.snapshot or not self.is_room_owner():
            return False
        if self.snapshot.room_status != poker_pb2.OPEN:
            return False
        active = [seat for seat in self.snapshot.seats if seat.player_id and seat.chips > 0]
        return len(active) >= 2 and all(seat.ready for seat in active)

    def can_add_bot(self) -> bool:
        if not self.snapshot or not self.is_room_owner():
            return False
        if self.snapshot.room_status != poker_pb2.OPEN or self.snapshot.phase != poker_pb2.WAITING:
            return False
        return any(not seat.player_id for seat in self.snapshot.seats)

    def available_actions(self) -> dict[str, bool]:
        actions = {"fold": False, "check": False, "call": False, "raise": False, "all_in": False}
        hero_seat = self.hero_seat()
        if not hero_seat or not hero_seat.is_turn or not self.snapshot:
            return actions

        facing_bet = hero_seat.committed < self.snapshot.current_bet
        chips_remaining = max(0, hero_seat.chips)
        call_amount = max(0, self.snapshot.current_bet - hero_seat.committed)
        min_raise_target = self.snapshot.current_bet + self.snapshot.min_raise
        max_target_bet = hero_seat.committed + chips_remaining

        actions["fold"] = True
        actions["check"] = not facing_bet
        actions["call"] = facing_bet and chips_remaining > 0
        actions["raise"] = max_target_bet >= min_raise_target and chips_remaining > call_amount
        actions["all_in"] = chips_remaining > 0
        return actions

    def draw(self, buttons: list[Button]) -> None:
        self.screen.fill(BG)
        if self.ui_state == "LOGIN":
            self.draw_login()
        elif self.ui_state == "LOBBY":
            self.draw_lobby()
        else:
            self.draw_room()
        for button in buttons:
            button.draw(self.screen, self.small)

    def draw_login(self) -> None:
        layout = self.login_layout()
        shell = layout["shell"]
        showcase = layout["showcase"]
        form = layout["form"]
        self.address_input.rect = layout["address"]
        self.name_input.rect = layout["name"]

        self.draw_login_background(shell)
        pygame.draw.rect(self.screen, PANEL, shell, border_radius=30)
        pygame.draw.rect(self.screen, LINE, shell, width=1, border_radius=30)
        self.draw_login_showcase(showcase, layout)

        pygame.draw.rect(self.screen, (18, 28, 34), form, border_radius=26)
        pygame.draw.rect(self.screen, (67, 88, 92), form, width=1, border_radius=26)
        draw_text(self.screen, self.small, "\u767b\u5f55\u7cfb\u7edf", form.x + 34, form.y + 30, GOLD)
        draw_text(self.screen, self.title_font, "\u8fdb\u5165\u5fb7\u5dde\u724c\u684c", form.x + 34, form.y + 58, TEXT)
        self.address_input.draw(self.screen, self.small, "\u670d\u52a1\u5668\u5730\u5740")
        self.name_input.draw(self.screen, self.small, "\u7528\u6237\u540d")

        avatar_card = layout["avatar_card"]
        pygame.draw.rect(self.screen, (22, 34, 40), avatar_card, border_radius=18)
        pygame.draw.rect(self.screen, (58, 80, 86), avatar_card, width=1, border_radius=18)
        preview_rect = layout["preview"]
        draw_text(self.screen, self.small, "当前头像", avatar_card.x + 18, avatar_card.y + 14, GOLD)
        self._login_avatar_hitboxes = []
        if self._avatar_picker_open:
            draw_text(self.screen, self.small, "选择头像", avatar_card.x + 18, avatar_card.y + 44, MUTED)
            self._login_avatar_hitboxes = self.login_avatar_hitboxes()
            for rect, avatar_id in self._login_avatar_hitboxes:
                draw_avatar(self.screen, rect, avatar_id, selected=avatar_id == self.selected_avatar_id)
        else:
            draw_avatar(self.screen, preview_rect, self.selected_avatar_id, selected=True)
        if self.ui_debug:
            self.draw_login_debug_overlay(layout)

    def draw_lobby(self) -> None:
        width, height = self.screen.get_size()
        draw_avatar(self.screen, pygame.Rect(28, 30, 38, 38), self.selected_avatar_id)
        draw_text(self.screen, self.title_font, "大厅列表", 78, 28, TEXT)
        draw_text(self.screen, self.small, f"当前玩家：{self.player_name}", 78, 76, MUTED)
        draw_text_clipped(self.screen, self.small, self.status, 30, 102, width - 60, MUTED)

        panel = pygame.Rect(28, 142, width - 56, height - 182)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, LINE, panel, width=1, border_radius=12)
        draw_text(self.screen, self.font, "房间", panel.x + 20, panel.y + 18, TEXT)

        columns = lobby_columns(panel)
        for header, x in zip(["房间", "房主", "人数", "准备", "状态"], columns):
            draw_text(self.screen, self.small, header, x, panel.y + 60, GOLD)

        self._room_hitboxes = []
        row_y = panel.y + 92
        for room in self.lobby_snapshot.rooms:
            row = pygame.Rect(panel.x + 16, row_y, panel.width - 32, 44)
            selected = room.room_id == self.selected_room_id
            pygame.draw.rect(self.screen, (40, 58, 63) if selected else PANEL_2, row, border_radius=10)
            pygame.draw.rect(self.screen, GOLD if selected else LINE, row, width=1, border_radius=10)
            draw_text_clipped(self.screen, self.small, room.display_name or room.room_id, row.x + 12, row.y + 11, columns[1] - columns[0] - 18, TEXT)
            draw_text_clipped(self.screen, self.small, room.owner_name or "-", columns[1], row.y + 11, columns[2] - columns[1] - 12, MUTED)
            draw_text_clipped(self.screen, self.small, f"{room.player_count}/{room.seat_count}", columns[2], row.y + 11, columns[3] - columns[2] - 12, MUTED)
            draw_text_clipped(self.screen, self.small, str(room.ready_count), columns[3], row.y + 11, columns[4] - columns[3] - 12, MUTED)
            draw_text_clipped(self.screen, self.small, room_status_label(room.room_status), columns[4], row.y + 11, row.right - columns[4] - 12, MUTED)
            self._room_hitboxes.append((row, room.room_id))
            row_y += 54

        if not self.lobby_snapshot.rooms:
            draw_centered(self.screen, self.font, "当前没有房间，先创建一个吧。", panel, MUTED)

    def draw_room(self) -> None:
        if not self.snapshot:
            return
        width, height = self.screen.get_size()
        draw_text(self.screen, self.title_font, self.snapshot.room_id, 26, 28, TEXT)
        owner_name = next((member.name for member in self.snapshot.members if member.is_owner), "-")
        draw_text(self.screen, self.small, f"房主：{owner_name}", 28, 78, MUTED)
        draw_text_clipped(self.screen, self.small, self.status, 28, 104, width - 56, MUTED)

        layout = self.room_layout(width, height)
        table = layout["table"]
        pygame.draw.ellipse(self.screen, FELT_DARK, table.inflate(42, 38))
        pygame.draw.ellipse(self.screen, FELT, table)
        pygame.draw.ellipse(self.screen, (41, 130, 94), table.inflate(-54, -46), width=3)

        self.draw_table(table)
        self.draw_room_side_panel(layout["side_panel"])

    def draw_table(self, table: pygame.Rect) -> None:
        phase = phase_label(self.snapshot.phase)
        top_line = f"{room_status_label(self.snapshot.room_status)} | {phase} | 底池 {self.snapshot.pot}"
        if self.snapshot.starting_countdown_seconds > 0:
            top_line += f" | {self.snapshot.starting_countdown_seconds} 秒后开始"
        draw_centered(self.screen, self.small, top_line, pygame.Rect(table.centerx - 260, table.y + 28, 520, 30), GOLD)

        card_gap = 64 if table.width >= 560 else 56
        card_width = 52 if table.width >= 560 else 46
        card_height = 74 if table.width >= 560 else 68
        board_width = card_width * 5 + (card_gap - card_width) * 4
        draw_cards(
            self.screen,
            self.card_font,
            self.snapshot.board,
            table.centerx - board_width // 2,
            table.centery - card_height // 2,
            reveal=True,
            gap=card_gap,
            card_size=(card_width, card_height),
        )

        positions = seat_positions(table, seat_rect_size(table))
        for seat in self.snapshot.seats:
            self.draw_seat(seat, positions[seat.seat_index])

        if self.snapshot.hero_cards:
            hero_total_width = card_width * 2 + (card_gap - card_width)
            draw_cards(
                self.screen,
                self.card_font,
                self.snapshot.hero_cards,
                table.centerx - hero_total_width // 2,
                table.bottom - (108 if table.height >= 340 else 96),
                reveal=True,
                count=2,
                gap=card_gap,
                card_size=(card_width, card_height),
            )

    def draw_seat(self, seat, rect: pygame.Rect) -> None:
        is_hero = bool(self.connection and seat.player_id == self.connection.player_id)
        fill = (52, 61, 55) if seat.player_id else (31, 43, 43)
        if seat.is_turn:
            fill = (85, 70, 33)
        pygame.draw.rect(self.screen, fill, rect, border_radius=10)
        pygame.draw.rect(self.screen, GOLD if is_hero else LINE, rect, width=2 if is_hero else 1, border_radius=10)

        name = seat.name if seat.player_id else f"空位 {seat.seat_index + 1}"
        status = []
        if seat.player_id and seat.player_id == self.snapshot.owner_player_id:
            status.append("房主")
        if seat.is_dealer:
            status.append("庄位")
        if seat.ready:
            status.append("已准备")
        if seat.folded:
            status.append("弃牌")
        if seat.all_in:
            status.append("全下")
        if seat.committed:
            status.append(f"下注 {seat.committed}")
        detail = " / ".join(status) if status else ("可入座" if not seat.player_id else f"筹码 {seat.chips}")
        chips = f"筹码 {seat.chips}" if seat.player_id else ""

        avatar_size = max(34, min(42, rect.height - 24))
        avatar_rect = pygame.Rect(rect.x + 10, rect.y + 10, avatar_size, avatar_size)
        avatar_id = seat.avatar_id if seat.avatar_id else DEFAULT_AVATAR_IDS[seat.seat_index % len(DEFAULT_AVATAR_IDS)]
        draw_avatar(self.screen, avatar_rect, avatar_id, placeholder=not seat.player_id)

        text_x = avatar_rect.right + 10
        max_width = rect.right - text_x - 8
        draw_text_clipped(self.screen, self.small, name, text_x, rect.y + 12, max_width, TEXT)
        draw_text_clipped(self.screen, self.small, detail, text_x, rect.y + 38, max_width, GOLD if seat.is_turn else MUTED)
        draw_text_clipped(self.screen, self.small, chips, text_x, rect.y + 62, max_width, MUTED)

    def draw_room_side_panel(self, panel: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, LINE, panel, width=1, border_radius=12)
        draw_text(self.screen, self.font, "房间信息", panel.x + 18, panel.y + 14, TEXT)
        info = [
            f"房间状态：{room_status_label(self.snapshot.room_status)}",
            f"当前下注：{self.snapshot.current_bet}",
            f"最小加注：{self.snapshot.min_raise}",
            f"手局数：{self.snapshot.hand_number}",
        ]
        if self.snapshot.starting_countdown_seconds > 0:
            info.append(f"倒计时：{self.snapshot.starting_countdown_seconds}s")
        for index, line in enumerate(info):
            draw_text_clipped(self.screen, self.small, line, panel.x + 18, panel.y + 54 + index * 24, panel.width - 36, MUTED)

        y = panel.y + 182
        draw_text(self.screen, self.small, "房间成员", panel.x + 18, y, GOLD)
        y += 28
        for member in self.snapshot.members[:8]:
            status = []
            if member.is_owner:
                status.append("房主")
            if member.seat_index >= 0:
                status.append(f"座位 {member.seat_index + 1}")
            if member.ready:
                status.append("已准备")
            draw_avatar(self.screen, pygame.Rect(panel.x + 18, y - 2, 18, 18), member.avatar_id)
            line = f"{member.name} - {' / '.join(status) if status else '观战'}"
            draw_text_clipped(self.screen, self.small, line, panel.x + 44, y, panel.width - 62, MUTED)
            y += 24

        y += 12
        result = self.snapshot.last_hand_result if self.snapshot.HasField("last_hand_result") else None
        if result and result.winner_seats:
            winners = ", ".join(str(seat + 1) for seat in result.winner_seats)
            draw_text_clipped(self.screen, self.small, f"上一手赢家: {winners}", panel.x + 18, y, panel.width - 36, GOLD)
            y += 26
            draw_text_clipped(self.screen, self.small, f"上一手ID: {result.hand_id}", panel.x + 18, y, panel.width - 36, MUTED)
        else:
            draw_text(self.screen, self.small, "最近日志", panel.x + 18, y, GOLD)
            y += 26
            for line in self.snapshot.log[-6:]:
                draw_text_clipped(self.screen, self.small, line, panel.x + 18, y, panel.width - 36, MUTED)
                y += 22

    def login_avatar_hitboxes(self) -> list[tuple[pygame.Rect, str]]:
        layout = self.login_layout()
        avatars_area = layout["avatars_area"]
        item_size = 64
        gap_x = 20
        gap_y = 18
        columns = 3
        grid_width = columns * item_size + (columns - 1) * gap_x
        start_x = avatars_area.x + max(0, (avatars_area.width - grid_width) // 2)
        grid_height = 2 * item_size + gap_y
        start_y = avatars_area.y + max(0, (avatars_area.height - grid_height) // 2)
        hitboxes: list[tuple[pygame.Rect, str]] = []
        for index, avatar_id in enumerate(DEFAULT_AVATAR_IDS):
            column = index % 3
            row = index // 3
            hitboxes.append(
                (
                    pygame.Rect(
                        start_x + column * (item_size + gap_x),
                        start_y + row * (item_size + gap_y),
                        item_size,
                        item_size,
                    ),
                    avatar_id,
                )
            )
        return hitboxes

    def login_layout(self) -> dict[str, pygame.Rect]:
        width, height = self.screen.get_size()
        cfg = self.ui_config["login"]
        shell_cfg = cfg["shell"]
        shell_margin_x = shell_cfg["margin_x"]
        shell_margin_y = shell_cfg["margin_y"]
        shell = pygame.Rect(
            shell_margin_x,
            shell_margin_y,
            min(max(shell_cfg["min_width"], width - shell_margin_x * 2), width - shell_margin_x * 2),
            min(shell_cfg["max_height"], height - shell_margin_y * 2),
        )
        shell.width = min(shell.width, width - shell_margin_x * 2)
        wide = shell.width >= cfg["breakpoint_wide"]
        if wide:
            showcase_inset = cfg["wide"]["showcase_inset"]
            showcase_gap = cfg["wide"]["panel_gap"]
            showcase_width = int(shell.width * cfg["wide"]["showcase_width_ratio"])
            showcase = pygame.Rect(
                shell.x + showcase_inset,
                shell.y + showcase_inset,
                showcase_width,
                shell.height - showcase_inset * 2,
            )
            form = pygame.Rect(
                showcase.right + showcase_gap,
                shell.y + showcase_inset,
                shell.right - showcase.right - showcase_gap - showcase_inset,
                shell.height - showcase_inset * 2,
            )
        else:
            narrow = cfg["narrow"]
            inset = narrow["panel_inset"]
            showcase = pygame.Rect(shell.x + inset, shell.y + inset, shell.width - inset * 2, narrow["showcase_height"])
            form = pygame.Rect(
                shell.x + inset,
                showcase.bottom + narrow["panel_gap"],
                shell.width - inset * 2,
                shell.bottom - showcase.bottom - (inset + narrow["panel_gap"]),
            )

        form_cfg = cfg["form"]
        avatar_cfg = cfg["avatar_card"]
        input_width = form.width - form_cfg["padding_x"] * 2
        input_x = form.x + form_cfg["padding_x"]
        address = pygame.Rect(input_x, form.y + form_cfg["address_y"], input_width, form_cfg["input_height"])
        name = pygame.Rect(input_x, form.y + form_cfg["name_y"], input_width, form_cfg["input_height"])
        button = pygame.Rect(input_x, form.bottom - form_cfg["button_bottom_offset"], input_width, form_cfg["button_height"])

        avatar_card_top = name.bottom + avatar_cfg["top_gap"]
        avatar_card_height = max(
            avatar_cfg["min_height_closed"],
            button.y - avatar_card_top - avatar_cfg["bottom_gap"],
        )
        if self._avatar_picker_open:
            avatar_card_height = max(avatar_card_height, avatar_cfg["min_height_open"])
        avatar_card = pygame.Rect(input_x, avatar_card_top, input_width, avatar_card_height)
        preview_size = min(avatar_cfg["preview_size"], avatar_card.height - avatar_cfg["preview_vertical_margin"] * 2)
        preview = pygame.Rect(
            avatar_card.x + avatar_cfg["preview_left"],
            avatar_card.y + (avatar_card.height - preview_size) // 2,
            preview_size,
            preview_size,
        )
        avatars_area = pygame.Rect(
            avatar_card.x + avatar_cfg["grid_padding_x"],
            avatar_card.y + avatar_cfg["grid_top"],
            avatar_card.width - avatar_cfg["grid_padding_x"] * 2,
            avatar_card.height - avatar_cfg["grid_top"] - avatar_cfg["grid_bottom"],
        )
        avatars_label = pygame.Rect(avatar_card.x + 18, avatar_card.y + 12, 120, 22)
        return {
            "shell": shell,
            "showcase": showcase,
            "form": form,
            "address": address,
            "name": name,
            "button": button,
            "avatar_card": avatar_card,
            "preview": preview,
            "avatars_area": avatars_area,
            "avatars_label": avatars_label,
        }

    def refresh_ui_config(self) -> None:
        if not self.ui_debug:
            return
        now = time.monotonic()
        if now - self._last_ui_config_check < 0.4:
            return
        self._last_ui_config_check = now
        self._load_ui_config(force=False)

    def _load_ui_config(self, force: bool) -> None:
        try:
            stat = UI_CONFIG_PATH.stat()
        except FileNotFoundError:
            if force:
                self.status = f"UI 配置文件缺失: {UI_CONFIG_PATH.name}"
            return
        if not force and self._ui_config_mtime == stat.st_mtime:
            return
        try:
            with UI_CONFIG_PATH.open("r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            self.ui_config = merge_login_ui_config(default_login_ui_config(), loaded)
            self._ui_config_mtime = stat.st_mtime
            if self.ui_debug:
                self.status = f"UI 配置已重载: {UI_CONFIG_PATH.name}"
        except Exception as exc:
            self.status = f"UI 配置读取失败: {exc}"

    def draw_login_debug_overlay(self, layout: dict[str, pygame.Rect]) -> None:
        debug_items = [
            (
                "shell",
                layout["shell"],
                {
                    "login.shell.margin_x": self.ui_config["login"]["shell"]["margin_x"],
                    "login.shell.margin_y": self.ui_config["login"]["shell"]["margin_y"],
                    "login.shell.min_width": self.ui_config["login"]["shell"]["min_width"],
                    "login.shell.max_height": self.ui_config["login"]["shell"]["max_height"],
                },
            ),
            (
                "showcase",
                layout["showcase"],
                {
                    "login.breakpoint_wide": self.ui_config["login"]["breakpoint_wide"],
                    "login.wide.showcase_width_ratio": self.ui_config["login"]["wide"]["showcase_width_ratio"],
                    "login.wide.showcase_inset": self.ui_config["login"]["wide"]["showcase_inset"],
                    "login.wide.panel_gap": self.ui_config["login"]["wide"]["panel_gap"],
                },
            ),
            (
                "form",
                layout["form"],
                {
                    "login.form.padding_x": self.ui_config["login"]["form"]["padding_x"],
                },
            ),
            (
                "address",
                layout["address"],
                {
                    "login.form.address_y": self.ui_config["login"]["form"]["address_y"],
                    "login.form.input_height": self.ui_config["login"]["form"]["input_height"],
                },
            ),
            (
                "name",
                layout["name"],
                {
                    "login.form.name_y": self.ui_config["login"]["form"]["name_y"],
                    "login.form.input_height": self.ui_config["login"]["form"]["input_height"],
                },
            ),
            (
                "avatar_card",
                layout["avatar_card"],
                {
                    "login.avatar_card.top_gap": self.ui_config["login"]["avatar_card"]["top_gap"],
                    "login.avatar_card.bottom_gap": self.ui_config["login"]["avatar_card"]["bottom_gap"],
                    "login.avatar_card.min_height_closed": self.ui_config["login"]["avatar_card"]["min_height_closed"],
                    "login.avatar_card.min_height_open": self.ui_config["login"]["avatar_card"]["min_height_open"],
                },
            ),
            (
                "preview",
                layout["preview"],
                {
                    "login.avatar_card.preview_size": self.ui_config["login"]["avatar_card"]["preview_size"],
                    "login.avatar_card.preview_left": self.ui_config["login"]["avatar_card"]["preview_left"],
                    "login.avatar_card.preview_vertical_margin": self.ui_config["login"]["avatar_card"]["preview_vertical_margin"],
                },
            ),
            (
                "button",
                layout["button"],
                {
                    "login.form.button_height": self.ui_config["login"]["form"]["button_height"],
                    "login.form.button_bottom_offset": self.ui_config["login"]["form"]["button_bottom_offset"],
                },
            ),
        ]
        for name, rect, values in debug_items:
            pygame.draw.rect(self.screen, (255, 120, 80), rect, width=2, border_radius=8)
            details = " ".join(f"{key}={value}" for key, value in values.items())
            label = f"{name} {rect.width}x{rect.height} @ {rect.x},{rect.y} | {details}"
            self.draw_debug_label(rect, label)

    def draw_debug_label(self, rect: pygame.Rect, label: str) -> None:
        text_surface = self.small.render(label, True, (255, 244, 190))
        text_rect = text_surface.get_rect()
        text_rect.x = rect.x
        text_rect.bottom = max(18, rect.y - 6)
        background = text_rect.inflate(12, 8)
        pygame.draw.rect(self.screen, (28, 18, 14), background, border_radius=8)
        pygame.draw.rect(self.screen, (255, 164, 88), background, width=1, border_radius=8)
        self.screen.blit(text_surface, text_rect)

    def room_layout(self, width: int, height: int) -> dict[str, pygame.Rect]:
        top = 150
        bottom_margin = 98
        available_height = max(260, height - top - bottom_margin)
        side_panel = pygame.Rect(width - SIDE_PANEL_WIDTH - 26, top, SIDE_PANEL_WIDTH, available_height)
        table_width = width - side_panel.width - 3 * LAYOUT_GAP
        stacked = table_width < MIN_TABLE_WIDTH + 40 or available_height < MIN_TABLE_HEIGHT + 70
        if stacked:
            side_height = min(240, max(180, available_height // 3))
            table = pygame.Rect(26, top, width - 52, max(MIN_TABLE_HEIGHT, available_height - side_height - 14))
            side_panel = pygame.Rect(26, table.bottom + 14, table.width, side_height)
        else:
            table = pygame.Rect(26, top, max(MIN_TABLE_WIDTH, table_width), max(MIN_TABLE_HEIGHT, available_height))
        return {"table": table, "side_panel": side_panel}

    def draw_login_background(self, shell: pygame.Rect) -> None:
        width, height = self.screen.get_size()
        for y in range(height):
            blend = y / max(1, height)
            color = (
                int(10 + 8 * blend),
                int(18 + 22 * blend),
                int(24 + 18 * blend),
            )
            pygame.draw.line(self.screen, color, (0, y), (width, y))
        pygame.draw.circle(self.screen, (23, 56, 49), (shell.x + 120, shell.y + 90), 170)
        pygame.draw.circle(self.screen, (18, 35, 48), (shell.right - 110, shell.bottom - 70), 220)
        pygame.draw.circle(self.screen, (120, 90, 35), (shell.right - 180, shell.y + 96), 72, width=2)

    def draw_login_showcase(self, showcase: pygame.Rect, layout: dict[str, pygame.Rect]) -> None:
        pygame.draw.rect(self.screen, (21, 55, 45), showcase, border_radius=26)
        pygame.draw.rect(self.screen, (58, 104, 88), showcase, width=1, border_radius=26)
        top_badge = pygame.Rect(showcase.x + 26, showcase.y + 24, 122, 28)
        pygame.draw.rect(self.screen, (31, 71, 61), top_badge, border_radius=14)
        draw_centered(self.screen, self.small, "德州牌局大厅", top_badge, GOLD)
        draw_text(self.screen, self.title_font, "Texas Hold'em", showcase.x + 26, showcase.y + 70, TEXT)
        draw_text(self.screen, self.font, "Online", showcase.x + 26, showcase.y + 112, TEXT)
        draw_text_clipped(
            self.screen,
            self.small,
            "快速连接服务器，选择身份后即可进入大厅，准备、入座、开局一气呵成。",
            showcase.x + 26,
            showcase.y + 158,
            showcase.width - 52,
            MUTED,
        )

        table_rect = pygame.Rect(showcase.x + 34, showcase.bottom - 188, showcase.width - 68, 126)
        pygame.draw.ellipse(self.screen, FELT_DARK, table_rect.inflate(26, 24))
        pygame.draw.ellipse(self.screen, FELT, table_rect)
        pygame.draw.ellipse(self.screen, (45, 139, 100), table_rect.inflate(-26, -22), width=3)
        draw_cards(self.screen, self.card_font, [], table_rect.centerx - 88, table_rect.y + 28, reveal=False, count=3, gap=60)
        draw_login_chip(self.screen, (table_rect.x + 42, table_rect.y + 34), RED)
        draw_login_chip(self.screen, (table_rect.right - 42, table_rect.y + 44), BLUE)
        draw_login_chip(self.screen, (table_rect.centerx + 72, table_rect.bottom - 34), GOLD)

        feature_y = showcase.y + 248
        for title, desc, color in [
            ("实时大厅", "进入后可直接查看房间状态与人数。", BLUE),
            ("快速入桌", "头像与昵称在登录时一次配置完成。", GREEN),
            ("响应式界面", "不同窗口比例下依旧保持清晰布局。", GOLD),
        ]:
            icon = pygame.Rect(showcase.x + 28, feature_y, 16, 16)
            pygame.draw.circle(self.screen, color, icon.center, 8)
            draw_text(self.screen, self.font, title, showcase.x + 56, feature_y - 6, TEXT)
            draw_text_clipped(self.screen, self.small, desc, showcase.x + 56, feature_y + 18, showcase.width - 84, MUTED)
            feature_y += 64


def draw_cards(
    surface: pygame.Surface,
    font: pygame.font.Font,
    cards,
    x: int,
    y: int,
    reveal: bool,
    count: int = 5,
    gap: int = 64,
    card_size: tuple[int, int] = (52, 74),
) -> None:
    card_width, card_height = card_size
    for index in range(count):
        rect = pygame.Rect(x + index * gap, y, card_width, card_height)
        pygame.draw.rect(surface, CARD, rect, border_radius=7)
        pygame.draw.rect(surface, (214, 205, 184), rect, width=1, border_radius=7)
        if reveal and index < len(cards):
            card = cards[index]
            label = f"{rank_label(card.rank)}{suit_label(card.suit)}"
            color = CARD_RED if card.suit in (poker_pb2.HEARTS, poker_pb2.DIAMONDS) else CARD_BLACK
            draw_centered(surface, font, label, rect, color)
        else:
            inset = 12 if card_width >= 52 else 10
            pygame.draw.rect(surface, (67, 103, 141), rect.inflate(-inset, -inset), border_radius=5)


def draw_avatar(
    surface: pygame.Surface,
    rect: pygame.Rect,
    avatar_id: str,
    *,
    selected: bool = False,
    placeholder: bool = False,
) -> None:
    theme = AVATAR_THEMES.get(avatar_id or DEFAULT_AVATAR_IDS[0], AVATAR_THEMES[DEFAULT_AVATAR_IDS[0]])
    frame = GOLD if selected else LINE
    pygame.draw.rect(surface, theme["bg"], rect, border_radius=14)
    pygame.draw.rect(surface, frame, rect, width=2 if selected else 1, border_radius=14)
    inner = rect.inflate(-8, -8)
    if placeholder:
        pygame.draw.circle(surface, MUTED, (inner.centerx, inner.y + inner.h // 3), max(6, inner.w // 7), width=2)
        pygame.draw.arc(surface, MUTED, (inner.x + 6, inner.centery - 2, inner.w - 12, inner.h // 2), 3.14, 0.0, 2)
        return
    pygame.draw.circle(surface, theme["accent"], (inner.centerx, inner.y + inner.h // 3), max(7, inner.w // 6))
    pygame.draw.circle(surface, theme["fg"], (inner.centerx, inner.y + inner.h // 3 + 2), max(6, inner.w // 7))
    body = pygame.Rect(inner.x + inner.w // 4, inner.y + inner.h // 2, inner.w // 2, inner.h // 3)
    pygame.draw.rect(surface, theme["fg"], body, border_radius=10)
    badge_w = max(14, rect.w // 3)
    badge = pygame.Rect(rect.right - badge_w - 4, rect.bottom - badge_w - 4, badge_w, badge_w)
    pygame.draw.ellipse(surface, theme["accent"], badge)


def draw_login_chip(surface: pygame.Surface, center: tuple[int, int], color: tuple[int, int, int]) -> None:
    pygame.draw.circle(surface, color, center, 16)
    pygame.draw.circle(surface, TEXT, center, 16, width=2)
    pygame.draw.circle(surface, (255, 255, 255), center, 8, width=2)
    for dx, dy in [(0, -12), (10, -6), (10, 6), (0, 12), (-10, 6), (-10, -6)]:
        pygame.draw.circle(surface, TEXT, (center[0] + dx, center[1] + dy), 2)


def seat_positions(table: pygame.Rect, seat_size: tuple[int, int]) -> list[pygame.Rect]:
    seat_w, seat_h = seat_size
    half_w = seat_w // 2
    bottom_margin = max(24, table.height // 8)
    side_inset = max(20, table.width // 24)
    upper_inset = max(18, table.height // 7)
    return [
        pygame.Rect(table.centerx - half_w, table.bottom - bottom_margin - seat_h, seat_w, seat_h),
        pygame.Rect(table.x + side_inset, table.centery + 24, seat_w, seat_h),
        pygame.Rect(table.x + side_inset + 10, table.y + upper_inset, seat_w, seat_h),
        pygame.Rect(table.centerx - half_w, table.y + 12, seat_w, seat_h),
        pygame.Rect(table.right - seat_w - side_inset - 10, table.y + upper_inset, seat_w, seat_h),
        pygame.Rect(table.right - seat_w - side_inset, table.centery + 24, seat_w, seat_h),
    ]


def seat_rect_size(table: pygame.Rect) -> tuple[int, int]:
    if table.width >= 720 and table.height >= 420:
        return (178, 96)
    if table.width >= 600:
        return (160, 90)
    return (142, 84)


def layout_button_row(right: int, y: int, width: int, height: int, count: int, gap: int) -> list[pygame.Rect]:
    total_width = count * width + max(0, count - 1) * gap
    start_x = right - total_width
    return [pygame.Rect(start_x + index * (width + gap), y, width, height) for index in range(count)]


def lobby_columns(panel: pygame.Rect) -> list[int]:
    usable_width = panel.width - 40
    fractions = [0.0, 0.42, 0.64, 0.78, 0.88]
    return [panel.x + 20 + int(usable_width * fraction) for fraction in fractions]


def draw_text(surface: pygame.Surface, font: pygame.font.Font, text: str, x: int, y: int, color) -> None:
    surface.blit(font.render(text, True, color), (x, y))


def draw_text_clipped(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    x: int,
    y: int,
    max_width: int,
    color,
) -> None:
    if max_width <= 0:
        return
    rendered_text = text
    if font.size(rendered_text)[0] > max_width:
        suffix = "..."
        while rendered_text and font.size(rendered_text + suffix)[0] > max_width:
            rendered_text = rendered_text[:-1]
        rendered_text = rendered_text + suffix if rendered_text else suffix
    draw_text(surface, font, rendered_text, x, y, color)


def draw_centered(surface: pygame.Surface, font: pygame.font.Font, text: str, rect: pygame.Rect, color) -> None:
    rendered = font.render(text, True, color)
    surface.blit(rendered, rendered.get_rect(center=rect.center))


def rank_label(rank: int) -> str:
    return {
        poker_pb2.TWO: "2",
        poker_pb2.THREE: "3",
        poker_pb2.FOUR: "4",
        poker_pb2.FIVE: "5",
        poker_pb2.SIX: "6",
        poker_pb2.SEVEN: "7",
        poker_pb2.EIGHT: "8",
        poker_pb2.NINE: "9",
        poker_pb2.TEN: "10",
        poker_pb2.JACK: "J",
        poker_pb2.QUEEN: "Q",
        poker_pb2.KING: "K",
        poker_pb2.ACE: "A",
    }.get(rank, "?")


def suit_label(suit: int) -> str:
    return {
        poker_pb2.CLUBS: "C",
        poker_pb2.DIAMONDS: "D",
        poker_pb2.HEARTS: "H",
        poker_pb2.SPADES: "S",
    }.get(suit, "?")


def phase_label(phase: int) -> str:
    return {
        poker_pb2.WAITING: "等待中",
        poker_pb2.PREFLOP: "翻牌前",
        poker_pb2.FLOP: "翻牌",
        poker_pb2.TURN: "转牌",
        poker_pb2.RIVER: "河牌",
        poker_pb2.SHOWDOWN: "摊牌",
        poker_pb2.HAND_COMPLETE: "本手结束",
    }.get(phase, "未知")


def room_status_label(status: int) -> str:
    return {
        poker_pb2.OPEN: "等待中",
        poker_pb2.STARTING: "倒计时中",
        poker_pb2.PLAYING: "对局中",
    }.get(status, "未知")


def parse_args():
    parser = ArgumentParser(description="Texas Holdem Online client")
    parser.add_argument("--ui-debug", action="store_true", help="Enable login UI debug overlay and hot reload.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    PokerApp(ui_debug=args.ui_debug).run()


if __name__ == "__main__":
    main()
