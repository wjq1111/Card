from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass

import pygame

from client.network import PokerClientConnection
from proto_gen import poker_pb2
from shared.game_logging import GameLogStore


WIDTH = 1180
HEIGHT = 720
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
MUTED = (150, 169, 163)
LINE = (54, 74, 78)
CARD = (247, 242, 226)
CARD_RED = (184, 43, 58)
CARD_BLACK = (30, 36, 39)


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
        pygame.draw.rect(surface, base, self.rect, border_radius=8)
        pygame.draw.rect(surface, LINE, self.rect, width=1, border_radius=8)
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
        draw_text(surface, font, label, self.rect.x, self.rect.y - 24, MUTED)
        border = GOLD if self.active else LINE
        pygame.draw.rect(surface, (18, 27, 31), self.rect, border_radius=8)
        pygame.draw.rect(surface, border, self.rect, width=1, border_radius=8)
        draw_text(surface, font, self.value, self.rect.x + 12, self.rect.y + 10, TEXT)


class DemoBot:
    def __init__(self, address: str, seat_index: int) -> None:
        self.name = f"Bot{random.randint(100, 999)}"
        self.seat_index = seat_index
        self.connection = PokerClientConnection(address)
        self.snapshot = None
        self.last_move_at = 0.0
        self.connection.send(poker_pb2.ClientEvent(join_room=poker_pb2.JoinRoom(room_id="lobby", name=self.name)))

    def update(self) -> None:
        for server_event in self.connection.poll():
            payload = server_event.WhichOneof("payload")
            if payload == "joined":
                self.connection.set_identity(server_event.joined.player_id, server_event.joined.reconnect_token)
                self.connection.send(poker_pb2.ClientEvent(sit_down=poker_pb2.SitDown(seat_index=self.seat_index)))
            elif payload == "snapshot":
                self.snapshot = server_event.snapshot

        if not self.snapshot:
            return

        bot_seat = next(
            (seat for seat in self.snapshot.seats if seat.player_id == self.connection.player_id),
            None,
        )
        if not bot_seat:
            return
        if not bot_seat.ready:
            self.connection.send(poker_pb2.ClientEvent(set_ready=poker_pb2.SetReady(ready=True)))
            return
        if time.monotonic() - self.last_move_at < 0.7 or not bot_seat.is_turn:
            return

        move_type = poker_pb2.CHECK if bot_seat.committed == self.snapshot.current_bet else poker_pb2.CALL
        self.connection.send(poker_pb2.ClientEvent(player_move=poker_pb2.PlayerMove(type=move_type)))
        self.last_move_at = time.monotonic()


class PokerApp:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Texas Holdem Online")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Microsoft YaHei UI", 19)
        self.small = pygame.font.SysFont("Microsoft YaHei UI", 15)
        self.title_font = pygame.font.SysFont("Microsoft YaHei UI", 30, bold=True)
        self.card_font = pygame.font.SysFont("Arial", 22, bold=True)

        self.address_input = TextInput(
            pygame.Rect(24, 92, 220, 42),
            os.getenv("POKER_SERVER", "119.45.157.13:50051"),
        )
        self.name_input = TextInput(pygame.Rect(260, 92, 170, 42), f"Player{random.randint(100, 999)}")
        self.connection: PokerClientConnection | None = None
        self.snapshot = None
        self.status = "填写地址和昵称后点击连接"
        self.bot: DemoBot | None = None
        self.last_heartbeat = time.monotonic()
        self.running = True
        self.log_store = GameLogStore("runtime_logs", "client", "anonymous")
        self._last_state_key: tuple[object, ...] | None = None

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
        self.address_input.handle(event)
        self.name_input.handle(event)
        for button in buttons:
            if button.hit(event):
                self.dispatch(button.action)

    def dispatch(self, action: str) -> None:
        if action == "connect":
            self.connect()
        elif action.startswith("sit:"):
            self.send(poker_pb2.ClientEvent(sit_down=poker_pb2.SitDown(seat_index=int(action.split(":")[1]))))
        elif action == "stand":
            self.send(poker_pb2.ClientEvent(stand_up=poker_pb2.StandUp()))
        elif action == "ready":
            hero_seat = self.hero_seat()
            if hero_seat:
                self.send(poker_pb2.ClientEvent(set_ready=poker_pb2.SetReady(ready=not hero_seat.ready)))
        elif action == "bot":
            self.add_bot()
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

    def connect(self) -> None:
        address = self.address_input.value.strip() or "119.45.157.13:50051"
        self.connection = PokerClientConnection(address)
        name = self.name_input.value.strip() or f"Player{random.randint(100, 999)}"
        self.connection.send(poker_pb2.ClientEvent(join_room=poker_pb2.JoinRoom(room_id="lobby", name=name)))
        self.status = f"正在连接 {self.connection.address} ..."
        self.log_local("Connecting to server", event_type="CLIENT", data={"address": address})

    def add_bot(self) -> None:
        if not self.connection:
            self.status = "请先连接房间"
            return
        used = {seat.seat_index for seat in self.snapshot.seats if seat.player_id} if self.snapshot else {0}
        seat_index = next((index for index in range(6) if index not in used), 1)
        self.bot = DemoBot(self.connection.address, seat_index)
        self.status = "已加入一个自动测试对手"

    def move(self, move_type: int, amount: int = 0) -> None:
        self.send(poker_pb2.ClientEvent(player_move=poker_pb2.PlayerMove(type=move_type, amount=amount)))

    def send(self, event: poker_pb2.ClientEvent) -> None:
        if not self.connection:
            self.status = "尚未连接服务器"
            return
        self.connection.send(event)

    def update_network(self) -> None:
        if self.bot:
            self.bot.update()

        if not self.connection:
            return

        if time.monotonic() - self.last_heartbeat > 5:
            self.send(poker_pb2.ClientEvent(heartbeat=poker_pb2.Heartbeat()))
            self.last_heartbeat = time.monotonic()

        for server_event in self.connection.poll():
            payload = server_event.WhichOneof("payload")
            if payload == "joined":
                self.connection.set_identity(server_event.joined.player_id, server_event.joined.reconnect_token)
                self.log_store = self.log_store.with_owner(server_event.joined.player_id)
                self.status = f"已进入房间 {server_event.joined.room_id}"
                self.log_local(
                    "Joined room",
                    event_type="JOIN",
                    data={"room_id": server_event.joined.room_id, "player_id": server_event.joined.player_id},
                )
            elif payload == "snapshot":
                self.snapshot = server_event.snapshot
                self.log_snapshot(server_event.snapshot)
            elif payload == "error":
                prefix = f"{server_event.error.code}: " if server_event.error.code else ""
                self.status = prefix + server_event.error.message
                self.log_local(
                    server_event.error.message,
                    event_type="ERROR",
                    data={"code": server_event.error.code},
                )
            elif payload == "server_notice":
                self.status = server_event.server_notice.message
                self.log_local(server_event.server_notice.message, event_type="NOTICE")

    def log_snapshot(self, snapshot) -> None:
        state_key = (
            snapshot.current_hand_id,
            snapshot.phase,
            snapshot.pot,
            snapshot.active_seat,
            snapshot.auto_start_countdown_seconds,
            snapshot.hand_number,
        )
        if state_key != self._last_state_key:
            self._last_state_key = state_key
            self.log_local(
                "Snapshot updated",
                event_type="SNAPSHOT",
                hand_id=snapshot.current_hand_id,
                data={
                    "phase": poker_pb2.GamePhase.Name(snapshot.phase),
                    "pot": snapshot.pot,
                    "active_seat": snapshot.active_seat,
                    "countdown": snapshot.auto_start_countdown_seconds,
                },
            )

    def log_local(
        self,
        message: str,
        *,
        event_type: str,
        hand_id: str = "",
        data: dict[str, object] | None = None,
    ) -> None:
        room_id = self.snapshot.room_id if self.snapshot else "lobby"
        hand_number = self.snapshot.hand_number if self.snapshot else 0
        phase = poker_pb2.GamePhase.Name(self.snapshot.phase) if self.snapshot else "CLIENT"
        self.log_store.write(
            room_id,
            message,
            phase=phase,
            event_type=event_type,
            hand_id=hand_id,
            hand_number=hand_number,
            data=data,
        )

    def make_buttons(self) -> list[Button]:
        width, height = self.screen.get_size()
        connected = self.connection is not None
        hero_seat = self.hero_seat()
        action_enabled = self.available_actions()
        can_toggle_ready = bool(hero_seat and self.snapshot and self.snapshot.phase in (poker_pb2.WAITING, poker_pb2.HAND_COMPLETE))
        ready_label = "取消准备" if hero_seat and hero_seat.ready else "准备"

        buttons = [
            Button(pygame.Rect(450, 92, 92, 42), "连接", "connect", BLUE),
            Button(pygame.Rect(554, 92, 110, 42), "测试对手", "bot", GREEN, connected),
        ]

        if hero_seat:
            buttons.append(Button(pygame.Rect(width - 314, 92, 112, 42), ready_label, "ready", GOLD, can_toggle_ready))
            buttons.append(Button(pygame.Rect(width - 190, 92, 112, 42), "离座", "stand", PANEL_2, connected))
        else:
            for index in range(6):
                occupied = bool(self.snapshot and self.snapshot.seats[index].player_id)
                buttons.append(
                    Button(
                        pygame.Rect(24 + index * 82, height - 66, 72, 38),
                        f"坐 {index + 1}",
                        f"sit:{index}",
                        PANEL_2,
                        connected and not occupied,
                    )
                )

        actions = [
            ("弃牌", "fold", RED, action_enabled["fold"]),
            ("过牌", "check", PANEL_2, action_enabled["check"]),
            ("跟注", "call", BLUE, action_enabled["call"]),
            ("加注", "raise", GOLD, action_enabled["raise"]),
            ("全下", "all_in", RED, action_enabled["all_in"]),
        ]
        for offset, (label, action, color, enabled) in enumerate(actions):
            buttons.append(Button(pygame.Rect(width - 520 + offset * 100, height - 66, 88, 38), label, action, color, enabled))
        return buttons

    def hero_seat(self):
        if not self.connection or not self.snapshot:
            return None
        return next((seat for seat in self.snapshot.seats if seat.player_id == self.connection.player_id), None)

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
        width, height = self.screen.get_size()
        self.screen.fill(BG)
        draw_text(self.screen, self.title_font, "Texas Holdem Online", 24, 22, TEXT)
        draw_text(self.screen, self.small, self.status, 26, 58, MUTED)
        self.address_input.draw(self.screen, self.small, "服务器")
        self.name_input.draw(self.screen, self.small, "昵称")

        table = pygame.Rect(290, 170, max(520, width - 580), max(330, height - 300))
        pygame.draw.ellipse(self.screen, FELT_DARK, table.inflate(38, 34))
        pygame.draw.ellipse(self.screen, FELT, table)
        pygame.draw.ellipse(self.screen, (41, 130, 94), table.inflate(-50, -42), width=3)

        if self.snapshot:
            self.draw_table(table)
            self.draw_side_panel(width, height)
        else:
            draw_centered(self.screen, self.font, "未连接房间", table, TEXT)

        for button in buttons:
            button.draw(self.screen, self.small)

    def draw_table(self, table: pygame.Rect) -> None:
        phase = phase_label(self.snapshot.phase)
        countdown = self.snapshot.auto_start_countdown_seconds
        top_line = f"{phase}  |  底池 {self.snapshot.pot}"
        if self.snapshot.phase == poker_pb2.WAITING and countdown > 0:
            top_line += f"  |  {countdown} 秒后开局"
        draw_centered(self.screen, self.small, top_line, pygame.Rect(table.centerx - 200, table.y + 28, 400, 30), GOLD)
        draw_cards(self.screen, self.card_font, self.snapshot.board, table.centerx - 158, table.centery - 44, reveal=True)

        positions = seat_positions(table)
        for seat in self.snapshot.seats:
            x, y = positions[seat.seat_index]
            self.draw_seat(seat, pygame.Rect(x, y, 150, 78))

        if self.snapshot.hero_cards:
            draw_cards(self.screen, self.card_font, self.snapshot.hero_cards, table.centerx - 62, table.bottom - 108, reveal=True, count=2)

    def draw_seat(self, seat, rect: pygame.Rect) -> None:
        is_hero = self.connection and seat.player_id == self.connection.player_id
        fill = (52, 61, 55) if seat.player_id else (31, 43, 43)
        if seat.is_turn:
            fill = (85, 70, 33)
        pygame.draw.rect(self.screen, fill, rect, border_radius=8)
        pygame.draw.rect(self.screen, GOLD if is_hero else LINE, rect, width=2 if is_hero else 1, border_radius=8)
        name = seat.name if seat.player_id else f"空位 {seat.seat_index + 1}"
        status = []
        if seat.is_dealer:
            status.append("庄")
        if seat.ready:
            status.append("准备")
        if seat.folded:
            status.append("弃牌")
        if seat.all_in:
            status.append("全下")
        if seat.committed:
            status.append(f"下注 {seat.committed}")
        detail = " / ".join(status) if status else (f"筹码 {seat.chips}" if seat.player_id else "可入座")
        chips = f"筹码 {seat.chips}" if seat.player_id else ""
        draw_text(self.screen, self.small, name, rect.x + 10, rect.y + 10, TEXT)
        draw_text(self.screen, self.small, detail, rect.x + 10, rect.y + 34, GOLD if seat.is_turn else MUTED)
        draw_text(self.screen, self.small, chips, rect.x + 10, rect.y + 56, MUTED)

    def draw_side_panel(self, width: int, height: int) -> None:
        panel = pygame.Rect(width - 270, 154, 246, height - 242)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=8)
        pygame.draw.rect(self.screen, LINE, panel, width=1, border_radius=8)
        draw_text(self.screen, self.font, "牌局信息", panel.x + 18, panel.y + 16, TEXT)
        info = [
            f"房间: {self.snapshot.room_id}",
            f"手数: {self.snapshot.hand_number}",
            f"当前下注: {self.snapshot.current_bet}",
            f"最小加注: {self.snapshot.min_raise}",
            f"手局ID: {self.snapshot.current_hand_id or '-'}",
        ]
        if self.snapshot.phase == poker_pb2.WAITING and self.snapshot.auto_start_countdown_seconds > 0:
            info.append(f"开局倒计时: {self.snapshot.auto_start_countdown_seconds}s")
        for index, line in enumerate(info):
            draw_text(self.screen, self.small, line, panel.x + 18, panel.y + 56 + index * 24, MUTED)

        y = panel.y + 190
        result = self.snapshot.last_hand_result if self.snapshot.HasField("last_hand_result") else None
        if result and result.winner_seats:
            winners = ", ".join(str(seat + 1) for seat in result.winner_seats)
            draw_text(self.screen, self.small, f"上一手赢家: {winners}", panel.x + 18, y, GOLD)
            y += 26
            draw_text(self.screen, self.small, f"上一手ID: {result.hand_id}", panel.x + 18, y, MUTED)
            y += 26
            for delta in result.chip_deltas[:4]:
                sign = "+" if delta.delta >= 0 else ""
                draw_text(self.screen, self.small, f"座位 {delta.seat_index + 1}: {sign}{delta.delta}", panel.x + 18, y, MUTED)
                y += 22
        else:
            draw_text(self.screen, self.small, "最近日志", panel.x + 18, y, GOLD)
            y += 26
            for line in self.snapshot.log[-8:]:
                draw_text(self.screen, self.small, line, panel.x + 18, y, MUTED)
                y += 22

        y += 12
        log_path = self.log_store.room_log_path(self.snapshot.room_id)
        draw_text(self.screen, self.small, "本地日志", panel.x + 18, y, GOLD)
        y += 24
        draw_text(self.screen, self.small, str(log_path), panel.x + 18, y, MUTED)


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


def seat_positions(table: pygame.Rect) -> list[tuple[int, int]]:
    return [
        (table.centerx - 75, table.bottom - 86),
        (table.x + 24, table.centery + 44),
        (table.x + 36, table.y + 56),
        (table.centerx - 75, table.y + 16),
        (table.right - 186, table.y + 56),
        (table.right - 174, table.centery + 44),
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


def main() -> None:
    PokerApp().run()


if __name__ == "__main__":
    main()
