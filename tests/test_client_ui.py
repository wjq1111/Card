from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from client.main import PokerApp
from proto_gen import poker_pb2


def proto_card(rank: int, suit: int) -> poker_pb2.Card:
    return poker_pb2.Card(rank=rank, suit=suit)


def build_snapshot(
    *,
    hero_id: str = "hero",
    phase: int = poker_pb2.WAITING,
    hero_turn: bool = False,
    hero_ready: bool = False,
    current_bet: int = 20,
    min_raise: int = 20,
    include_result: bool = False,
) -> poker_pb2.RoomSnapshot:
    snapshot = poker_pb2.RoomSnapshot(
        room_id="lobby",
        hero_player_id=hero_id,
        phase=phase,
        pot=40,
        current_bet=current_bet,
        min_raise=min_raise,
        dealer_seat=0,
        active_seat=0 if hero_turn else 1,
        hand_number=3,
        current_hand_id="lobby-0003",
        auto_start_countdown_seconds=2 if phase == poker_pb2.WAITING else 0,
    )
    snapshot.hero_cards.extend(
        [
            proto_card(poker_pb2.ACE, poker_pb2.SPADES),
            proto_card(poker_pb2.KING, poker_pb2.HEARTS),
        ]
    )
    snapshot.board.extend(
        [
            proto_card(poker_pb2.TWO, poker_pb2.CLUBS),
            proto_card(poker_pb2.SEVEN, poker_pb2.DIAMONDS),
            proto_card(poker_pb2.NINE, poker_pb2.HEARTS),
        ]
    )
    snapshot.log.extend(["Alice joined room", "Hand 3 started"])
    for seat_index in range(6):
        seat = snapshot.seats.add()
        seat.seat_index = seat_index
        if seat_index == 0:
            seat.player_id = hero_id
            seat.name = "Alice"
            seat.chips = 1980
            seat.committed = current_bet if hero_turn else 10
            seat.ready = hero_ready
            seat.is_dealer = True
            seat.is_turn = hero_turn
            seat.hole_card_count = 2
            seat.hand_committed = 20
            seat.acted_this_round = not hero_turn
        elif seat_index == 1:
            seat.player_id = "villain"
            seat.name = "Bob"
            seat.chips = 1980
            seat.committed = current_bet
            seat.ready = True
            seat.is_turn = not hero_turn
            seat.hole_card_count = 2
            seat.hand_committed = 20
            seat.acted_this_round = True
        else:
            seat.chips = 2000
    if include_result:
        result = poker_pb2.HandResult(hand_id="lobby-0002", hand_number=2)
        result.winner_seats.extend([1])
        result.board.extend(snapshot.board)
        result.shown_hands.add(
            seat_index=1,
            cards=[proto_card(poker_pb2.QUEEN, poker_pb2.CLUBS), proto_card(poker_pb2.JACK, poker_pb2.SPADES)],
            hand_name="Two Pair",
        )
        result.chip_deltas.add(seat_index=0, delta=-20, final_stack=1980)
        result.chip_deltas.add(seat_index=1, delta=20, final_stack=2020)
        snapshot.last_hand_result.CopyFrom(result)
    return snapshot


class FakeConnection:
    def __init__(self, address: str = "127.0.0.1:50051") -> None:
        self.address = address
        self.player_id = ""
        self.reconnect_token = ""
        self.sent: list[poker_pb2.ClientEvent] = []
        self.pending_events: list[poker_pb2.ServerEvent] = []

    def send(self, event: poker_pb2.ClientEvent) -> None:
        self.sent.append(event)

    def set_identity(self, player_id: str, reconnect_token: str) -> None:
        self.player_id = player_id
        self.reconnect_token = reconnect_token

    def poll(self) -> list[poker_pb2.ServerEvent]:
        events = list(self.pending_events)
        self.pending_events.clear()
        return events


class PokerAppUiTest(unittest.TestCase):
    def setUp(self) -> None:
        pygame.init()
        pygame.font.init()
        self.addCleanup(pygame.quit)
        self.addCleanup(pygame.display.quit)
        self.app = PokerApp()

    def test_waiting_snapshot_enables_ready_but_not_action_buttons(self) -> None:
        connection = FakeConnection()
        connection.player_id = "hero"
        self.app.connection = connection
        self.app.snapshot = build_snapshot(hero_ready=False)

        buttons = {button.action: button for button in self.app.make_buttons()}

        self.assertTrue(buttons["ready"].enabled)
        self.assertEqual(buttons["ready"].label, "准备")
        self.assertFalse(buttons["fold"].enabled)
        self.assertFalse(buttons["check"].enabled)
        self.assertFalse(buttons["call"].enabled)
        self.assertFalse(buttons["raise"].enabled)
        self.assertFalse(buttons["all_in"].enabled)

    def test_turn_snapshot_enables_action_buttons_and_raise_dispatch(self) -> None:
        connection = FakeConnection()
        connection.player_id = "hero"
        self.app.connection = connection
        self.app.snapshot = build_snapshot(
            phase=poker_pb2.PREFLOP,
            hero_turn=True,
            hero_ready=True,
            current_bet=40,
            min_raise=40,
        )

        buttons = {button.action: button for button in self.app.make_buttons()}

        self.assertTrue(buttons["fold"].enabled)
        self.assertTrue(buttons["check"].enabled)
        self.assertFalse(buttons["call"].enabled)
        self.assertTrue(buttons["raise"].enabled)
        self.assertTrue(buttons["all_in"].enabled)

        self.app.dispatch("raise")

        move = connection.sent[-1].player_move
        self.assertEqual(move.type, poker_pb2.RAISE)
        self.assertEqual(move.amount, 80)

    def test_facing_bet_enables_call_and_disables_check(self) -> None:
        connection = FakeConnection()
        connection.player_id = "hero"
        self.app.connection = connection
        self.app.snapshot = build_snapshot(
            phase=poker_pb2.PREFLOP,
            hero_turn=True,
            hero_ready=True,
            current_bet=40,
            min_raise=40,
        )
        self.app.snapshot.seats[0].committed = 20

        buttons = {button.action: button for button in self.app.make_buttons()}

        self.assertTrue(buttons["fold"].enabled)
        self.assertFalse(buttons["check"].enabled)
        self.assertTrue(buttons["call"].enabled)
        self.assertTrue(buttons["raise"].enabled)
        self.assertTrue(buttons["all_in"].enabled)

    def test_connect_uses_entered_address_and_name(self) -> None:
        created_connections: list[FakeConnection] = []

        def fake_factory(address: str) -> FakeConnection:
            connection = FakeConnection(address)
            created_connections.append(connection)
            return connection

        self.app.address_input.value = "127.0.0.1:60001"
        self.app.name_input.value = "Alice"
        with patch("client.main.PokerClientConnection", side_effect=fake_factory):
            self.app.connect()

        self.assertEqual(len(created_connections), 1)
        self.assertEqual(created_connections[0].address, "127.0.0.1:60001")
        self.assertEqual(created_connections[0].sent[0].join_room.name, "Alice")
        self.assertIn("正在连接 127.0.0.1:60001", self.app.status)

    def test_update_network_applies_join_snapshot_and_error_feedback(self) -> None:
        connection = FakeConnection()
        self.app.connection = connection
        snapshot = build_snapshot(hero_ready=True)
        connection.pending_events = [
            poker_pb2.ServerEvent(
                joined=poker_pb2.Joined(player_id="hero", room_id="lobby", reconnect_token="token-1")
            ),
            poker_pb2.ServerEvent(snapshot=snapshot),
            poker_pb2.ServerEvent(error=poker_pb2.Error(code="INVALID_ACTION", message="不能在非自己回合操作")),
        ]

        self.app.update_network()

        self.assertEqual(connection.player_id, "hero")
        self.assertEqual(connection.reconnect_token, "token-1")
        self.assertEqual(self.app.snapshot.room_id, "lobby")
        self.assertEqual(self.app.status, "INVALID_ACTION: 不能在非自己回合操作")

    def test_draw_renders_last_hand_result_path_without_crashing(self) -> None:
        connection = FakeConnection()
        connection.player_id = "hero"
        self.app.connection = connection
        self.app.snapshot = build_snapshot(include_result=True)

        rendered_text: list[str] = []

        def capture_text(surface, font, text, x, y, color) -> None:
            rendered_text.append(text)

        with patch("client.main.draw_text", side_effect=capture_text):
            self.app.draw(self.app.make_buttons())

        self.assertIn("上一手赢家: 2", rendered_text)
        self.assertIn("上一手ID: lobby-0002", rendered_text)


if __name__ == "__main__":
    unittest.main()
