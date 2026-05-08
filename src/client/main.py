from __future__ import annotations

import ctypes
import os
import random
import time
from dataclasses import dataclass

import pygame

from src.client.network import PokerClientConnection
from src.proto_gen import poker_pb2
from src.shared.game_logging import GameLogStore


WIDTH = 1280
HEIGHT = 780
FPS = 60

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
        draw_text(surface, font, self.value, self.rect.x + 14, self.rect.y + 11, TEXT)


class PokerApp:
    def __init__(self) -> None:
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
        self.status = "请输入用户名后进入大厅"
        self.last_heartbeat = time.monotonic()
        self.running = True
        self.log_store = GameLogStore("runtime_logs", "client", "anonymous")
        self._last_state_key: tuple[object, ...] | None = None
        self._login_avatar_hitboxes: list[tuple[pygame.Rect, str]] = []
        self._room_hitboxes: list[tuple[pygame.Rect, str]] = []

    def run(self) -> None:
        while self.running:
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
            for rect, avatar_id in self.login_avatar_hitboxes():
                if rect.collidepoint(event.pos):
                    self.selected_avatar_id = avatar_id
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
            self.status = "用户名不能为空"
            return
        address = self.address_input.value.strip() or "119.45.157.13:50051"
        self.player_name = name
        self.connection = PokerClientConnection(address)
        self.connection.send(
            poker_pb2.ClientEvent(login=poker_pb2.Login(name=name, avatar_id=self.selected_avatar_id))
        )
        self.status = f"正在连接 {address} ..."

    def move(self, move_type: int, amount: int = 0) -> None:
        self.send(poker_pb2.ClientEvent(player_move=poker_pb2.PlayerMove(type=move_type, amount=amount)))

    def send(self, event: poker_pb2.ClientEvent) -> None:
        if not self.connection:
            self.status = "尚未连接服务器"
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
                self.status = f"欢迎回来，{self.player_name}"
            elif payload == "lobby_snapshot":
                self.lobby_snapshot = server_event.lobby_snapshot
                self.ui_state = "LOBBY"
                self.snapshot = None
                if self.selected_room_id and not any(
                    room.room_id == self.selected_room_id for room in self.lobby_snapshot.rooms
                ):
                    self.selected_room_id = ""
                self.status = f"大厅房间数: {len(self.lobby_snapshot.rooms)}"
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
            return [
                Button(pygame.Rect(542, 430, 200, 48), "进入大厅", "login", BLUE),
            ]
        if self.ui_state == "LOBBY":
            return self.make_lobby_buttons()
        return self.make_room_buttons()

    def make_lobby_buttons(self) -> list[Button]:
        width, _ = self.screen.get_size()
        has_selection = bool(self.selected_room_id)
        return [
            Button(pygame.Rect(width - 404, 42, 112, 42), "刷新", "refresh", PANEL_2, self.connection is not None),
            Button(pygame.Rect(width - 280, 42, 112, 42), "创建房间", "create_room", GREEN, self.connection is not None),
            Button(pygame.Rect(width - 156, 42, 112, 42), "加入房间", "join_room", BLUE, has_selection),
        ]

    def make_room_buttons(self) -> list[Button]:
        width, height = self.screen.get_size()
        buttons: list[Button] = [
            Button(pygame.Rect(width - 150, 42, 106, 42), "离开房间", "leave_room", PANEL_2, True),
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
            buttons.append(Button(pygame.Rect(width - 384, 42, 106, 42), ready_label, "ready", GOLD, can_toggle_ready))
            buttons.append(
                Button(
                    pygame.Rect(width - 270, 42, 106, 42),
                    "离座",
                    "stand",
                    PANEL_2,
                    self.snapshot and self.snapshot.room_status == poker_pb2.OPEN,
                )
            )
        if self.is_room_owner():
            buttons.append(
                Button(
                    pygame.Rect(width - 498, 42, 106, 42),
                    "开始游戏",
                    "start_game",
                    GREEN,
                    self.can_start_game(),
                )
            )

        for index in range(6):
            occupied = bool(self.snapshot and self.snapshot.seats[index].player_id)
            seat_enabled = bool(
                self.snapshot
                and self.snapshot.room_status == poker_pb2.OPEN
                and ((self.hero_seat() and not occupied) or (not self.hero_seat() and not occupied))
            )
            buttons.append(
                Button(
                    pygame.Rect(26 + index * 92, height - 66, 82, 40),
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
        for offset, (label, action, color, enabled) in enumerate(specs):
            buttons.append(Button(pygame.Rect(width - 530 + offset * 102, height - 66, 90, 40), label, action, color, enabled))
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
        width, height = self.screen.get_size()
        panel = pygame.Rect(max(72, width // 2 - 360), 120, min(720, width - 144), min(520, height - 180))
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=22)
        pygame.draw.rect(self.screen, LINE, panel, width=1, border_radius=22)
        draw_centered(self.screen, self.title_font, "Texas Holdem Online", pygame.Rect(panel.x, panel.y + 24, panel.w, 48), TEXT)
        draw_centered(
            self.screen,
            self.small,
            "选择昵称和默认头像后进入大厅",
            pygame.Rect(panel.x, panel.y + 70, panel.w, 24),
            MUTED,
        )
        self.address_input.draw(self.screen, self.small, "服务器地址")
        self.name_input.draw(self.screen, self.small, "用户名")
        preview_rect = pygame.Rect(panel.x + 36, panel.y + 164, 120, 120)
        draw_avatar(self.screen, preview_rect, self.selected_avatar_id, selected=True)
        draw_centered(
            self.screen,
            self.small,
            "当前头像",
            pygame.Rect(preview_rect.x - 10, preview_rect.bottom + 8, preview_rect.w + 20, 20),
            GOLD,
        )
        draw_text(self.screen, self.small, "默认头像", panel.x + 196, panel.y + 146, GOLD)
        self._login_avatar_hitboxes = self.login_avatar_hitboxes()
        for rect, avatar_id in self._login_avatar_hitboxes:
            draw_avatar(self.screen, rect, avatar_id, selected=avatar_id == self.selected_avatar_id)
        draw_centered(self.screen, self.small, self.status, pygame.Rect(0, panel.bottom - 48, width, 28), MUTED)

    def draw_lobby(self) -> None:
        width, height = self.screen.get_size()
        draw_avatar(self.screen, pygame.Rect(28, 30, 38, 38), self.selected_avatar_id)
        draw_text(self.screen, self.title_font, "大厅列表", 78, 28, TEXT)
        draw_text(self.screen, self.small, f"当前玩家: {self.player_name}", 78, 76, MUTED)
        draw_text(self.screen, self.small, self.status, 30, 102, MUTED)

        panel = pygame.Rect(28, 142, width - 56, height - 182)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, LINE, panel, width=1, border_radius=12)
        draw_text(self.screen, self.font, "房间", panel.x + 20, panel.y + 18, TEXT)

        headers = ["房间", "房主", "人数", "准备", "状态"]
        xs = [panel.x + 20, panel.x + 360, panel.x + 580, panel.x + 700, panel.x + 840]
        for header, x in zip(headers, xs):
            draw_text(self.screen, self.small, header, x, panel.y + 60, GOLD)

        self._room_hitboxes = []
        row_y = panel.y + 92
        for room in self.lobby_snapshot.rooms:
            row = pygame.Rect(panel.x + 16, row_y, panel.width - 32, 44)
            selected = room.room_id == self.selected_room_id
            pygame.draw.rect(self.screen, (40, 58, 63) if selected else PANEL_2, row, border_radius=10)
            pygame.draw.rect(self.screen, GOLD if selected else LINE, row, width=1, border_radius=10)
            draw_text(self.screen, self.small, room.display_name or room.room_id, row.x + 12, row.y + 11, TEXT)
            draw_text(self.screen, self.small, room.owner_name or "-", row.x + 352, row.y + 11, MUTED)
            draw_text(self.screen, self.small, f"{room.player_count}/{room.seat_count}", row.x + 572, row.y + 11, MUTED)
            draw_text(self.screen, self.small, str(room.ready_count), row.x + 692, row.y + 11, MUTED)
            draw_text(self.screen, self.small, room_status_label(room.room_status), row.x + 832, row.y + 11, MUTED)
            self._room_hitboxes.append((row, room.room_id))
            row_y += 54

        if not self.lobby_snapshot.rooms:
            draw_centered(self.screen, self.font, "当前没有房间，先创建一个吧", panel, MUTED)

    def draw_room(self) -> None:
        if not self.snapshot:
            return
        width, height = self.screen.get_size()
        draw_text(self.screen, self.title_font, self.snapshot.room_id, 26, 28, TEXT)
        owner_name = next((member.name for member in self.snapshot.members if member.is_owner), "-")
        draw_text(self.screen, self.small, f"房主: {owner_name}", 28, 78, MUTED)
        draw_text(self.screen, self.small, self.status, 28, 104, MUTED)

        table = pygame.Rect(290, 156, max(520, width - 600), max(360, height - 270))
        pygame.draw.ellipse(self.screen, FELT_DARK, table.inflate(42, 38))
        pygame.draw.ellipse(self.screen, FELT, table)
        pygame.draw.ellipse(self.screen, (41, 130, 94), table.inflate(-54, -46), width=3)

        self.draw_table(table)
        self.draw_room_side_panel(width, height)

    def draw_table(self, table: pygame.Rect) -> None:
        phase = phase_label(self.snapshot.phase)
        top_line = f"{room_status_label(self.snapshot.room_status)} | {phase} | 底池 {self.snapshot.pot}"
        if self.snapshot.starting_countdown_seconds > 0:
            top_line += f" | {self.snapshot.starting_countdown_seconds} 秒后开始"
        draw_centered(self.screen, self.small, top_line, pygame.Rect(table.centerx - 260, table.y + 28, 520, 30), GOLD)
        draw_cards(self.screen, self.card_font, self.snapshot.board, table.centerx - 158, table.centery - 44, reveal=True)

        positions = seat_positions(table)
        for seat in self.snapshot.seats:
            x, y = positions[seat.seat_index]
            self.draw_seat(seat, pygame.Rect(x, y, 178, 96))

        if self.snapshot.hero_cards:
            draw_cards(
                self.screen,
                self.card_font,
                self.snapshot.hero_cards,
                table.centerx - 62,
                table.bottom - 108,
                reveal=True,
                count=2,
            )

    def draw_seat(self, seat, rect: pygame.Rect) -> None:
        is_hero = self.connection and seat.player_id == self.connection.player_id
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
            status.append("庄")
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
        avatar_rect = pygame.Rect(rect.x + 10, rect.y + 12, 42, 42)
        avatar_id = seat.avatar_id if seat.avatar_id else DEFAULT_AVATAR_IDS[seat.seat_index % len(DEFAULT_AVATAR_IDS)]
        draw_avatar(self.screen, avatar_rect, avatar_id, placeholder=not seat.player_id)
        draw_text(self.screen, self.small, name, rect.x + 62, rect.y + 12, TEXT)
        draw_text(self.screen, self.small, detail, rect.x + 62, rect.y + 38, GOLD if seat.is_turn else MUTED)
        draw_text(self.screen, self.small, chips, rect.x + 62, rect.y + 62, MUTED)

    def draw_room_side_panel(self, width: int, height: int) -> None:
        panel = pygame.Rect(width - 278, 150, 252, height - 236)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=12)
        pygame.draw.rect(self.screen, LINE, panel, width=1, border_radius=12)
        draw_text(self.screen, self.font, "房间信息", panel.x + 18, panel.y + 14, TEXT)
        info = [
            f"房间状态: {room_status_label(self.snapshot.room_status)}",
            f"当前下注: {self.snapshot.current_bet}",
            f"最小加注: {self.snapshot.min_raise}",
            f"手局数: {self.snapshot.hand_number}",
        ]
        if self.snapshot.starting_countdown_seconds > 0:
            info.append(f"开始倒计时: {self.snapshot.starting_countdown_seconds}s")
        for index, line in enumerate(info):
            draw_text(self.screen, self.small, line, panel.x + 18, panel.y + 54 + index * 24, MUTED)

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
            draw_text(self.screen, self.small, line, panel.x + 44, y, MUTED)
            y += 24

        y += 12
        result = self.snapshot.last_hand_result if self.snapshot.HasField("last_hand_result") else None
        if result and result.winner_seats:
            draw_text(self.screen, self.small, f"上一手赢家: {', '.join(str(seat + 1) for seat in result.winner_seats)}", panel.x + 18, y, GOLD)
            y += 26
            draw_text(self.screen, self.small, f"上一手ID: {result.hand_id}", panel.x + 18, y, MUTED)
            y += 26
        else:
            draw_text(self.screen, self.small, "最近日志", panel.x + 18, y, GOLD)
            y += 26
            for line in self.snapshot.log[-6:]:
                draw_text(self.screen, self.small, line, panel.x + 18, y, MUTED)
                y += 22

    def login_avatar_hitboxes(self) -> list[tuple[pygame.Rect, str]]:
        width, _ = self.screen.get_size()
        panel_x = max(72, width // 2 - 360)
        panel_y = 120
        start_x = panel_x + 196
        start_y = panel_y + 176
        hitboxes: list[tuple[pygame.Rect, str]] = []
        for index, avatar_id in enumerate(DEFAULT_AVATAR_IDS):
            column = index % 3
            row = index // 3
            hitboxes.append((pygame.Rect(start_x + column * 88, start_y + row * 88, 64, 64), avatar_id))
        return hitboxes


def draw_cards(
    surface: pygame.Surface,
    font: pygame.font.Font,
    cards,
    x: int,
    y: int,
    reveal: bool,
    count: int = 5,
) -> None:
    for index in range(count):
        rect = pygame.Rect(x + index * 64, y, 52, 74)
        pygame.draw.rect(surface, CARD, rect, border_radius=7)
        pygame.draw.rect(surface, (214, 205, 184), rect, width=1, border_radius=7)
        if reveal and index < len(cards):
            card = cards[index]
            label = f"{rank_label(card.rank)}{suit_label(card.suit)}"
            color = CARD_RED if card.suit in (poker_pb2.HEARTS, poker_pb2.DIAMONDS) else CARD_BLACK
            draw_centered(surface, font, label, rect, color)
        else:
            pygame.draw.rect(surface, (67, 103, 141), rect.inflate(-12, -12), border_radius=5)


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


def seat_positions(table: pygame.Rect) -> list[tuple[int, int]]:
    return [
        (table.centerx - 81, table.bottom - 90),
        (table.x + 20, table.centery + 48),
        (table.x + 34, table.y + 58),
        (table.centerx - 81, table.y + 12),
        (table.right - 196, table.y + 58),
        (table.right - 182, table.centery + 48),
    ]


def draw_text(surface: pygame.Surface, font: pygame.font.Font, text: str, x: int, y: int, color) -> None:
    surface.blit(font.render(text, True, color), (x, y))


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
        poker_pb2.WAITING: "等待",
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


def main() -> None:
    PokerApp().run()


if __name__ == "__main__":
    main()
