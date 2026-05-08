import random
import unittest
from tempfile import TemporaryDirectory

from src.server.chip_store import PlayerChipStore
from src.shared.cards import Card
from src.shared.game_logging import GameLogStore
from src.server.room import Phase, PokerRoom, RoomStatus


def c(rank: str, suit: str) -> Card:
    return Card(suit=suit, rank=rank)


class RoomRulesTest(unittest.TestCase):
    def seated_heads_up_room(self) -> PokerRoom:
        room = PokerRoom("test", rng=random.Random(0))
        room.join("p1", "Alice")
        room.join("p2", "Bob")
        room.sit("p1", 0)
        room.sit("p2", 1)
        room.set_ready("p1", True)
        room.set_ready("p2", True)
        return room

    def act_current(self, room: PokerRoom, move: str, amount: int = 0) -> None:
        player_id = room.seats[room.active_seat].player_id
        room.player_move(player_id, move, amount)

    def test_owner_can_request_start_and_countdown_begins(self) -> None:
        room = self.seated_heads_up_room()

        room.request_start("p1", now=100.0)

        self.assertEqual(room.room_status, RoomStatus.STARTING)
        self.assertEqual(room.starting_countdown_seconds(100.0), 5)

    def test_heads_up_dealer_posts_small_blind_and_acts_preflop(self) -> None:
        room = self.seated_heads_up_room()
        room.start_hand()

        self.assertIn(room.dealer_seat, (0, 1))
        other = 1 if room.dealer_seat == 0 else 0
        self.assertEqual(room.seats[room.dealer_seat].committed, 10)
        self.assertEqual(room.seats[other].committed, 20)
        self.assertEqual(room.active_seat, room.dealer_seat)

    def test_postflop_check_does_not_end_round_until_everyone_acts(self) -> None:
        room = self.seated_heads_up_room()
        room.start_hand()

        self.act_current(room, "CALL")
        self.act_current(room, "CHECK")
        self.assertEqual(room.phase, Phase.FLOP)

        first_actor = room.active_seat
        self.act_current(room, "CHECK")

        self.assertEqual(room.phase, Phase.FLOP)
        self.assertNotEqual(room.active_seat, first_actor)

    def test_uncontested_pot_is_awarded_when_everyone_else_folds(self) -> None:
        room = self.seated_heads_up_room()
        room.start_hand()
        pot = room.pot

        loser = room.seats[room.active_seat].player_id
        winner = "p1" if loser == "p2" else "p2"
        room.player_move(loser, "FOLD")

        self.assertEqual(room.phase, Phase.HAND_COMPLETE)
        self.assertEqual(room.pot, 0)
        self.assertEqual(room.find_seat(winner).chips, 2000 - 20 + pot if winner != room.seats[room.dealer_seat].player_id else 2000 - 10 + pot)
        self.assertIsNotNone(room.last_hand_summary)

    def test_raise_below_minimum_is_rejected(self) -> None:
        room = self.seated_heads_up_room()
        room.start_hand()
        raiser = room.seats[room.active_seat].player_id

        with self.assertRaisesRegex(ValueError, "minimum"):
            room.player_move(raiser, "RAISE", 30)

    def test_short_all_in_updates_call_amount_without_full_raise(self) -> None:
        room = PokerRoom("test", rng=random.Random(0))
        for index in range(3):
            player_id = f"p{index}"
            room.join(player_id, f"Player {index}")
            room.sit(player_id, index)
            room.set_ready(player_id, True)
        room.start_hand()
        current_actor = room.seats[room.active_seat]
        current_actor.chips = 25

        room.player_move(current_actor.player_id, "ALL_IN")

        self.assertEqual(room.current_bet, 25)
        self.assertEqual(room.min_raise, 20)
        self.assertTrue(current_actor.acted_this_round)

    def test_showdown_records_hand_summary(self) -> None:
        room = self.seated_heads_up_room()
        room.start_hand()
        room.deck = [
            c("TWO", "CLUBS"),
            c("SEVEN", "DIAMONDS"),
            c("NINE", "HEARTS"),
            c("JACK", "SPADES"),
            c("QUEEN", "CLUBS"),
        ]

        self.act_current(room, "CALL")
        self.act_current(room, "CHECK")
        self.act_current(room, "CHECK")
        self.act_current(room, "CHECK")
        self.act_current(room, "CHECK")
        self.act_current(room, "CHECK")
        self.act_current(room, "CHECK")
        self.act_current(room, "CHECK")

        self.assertEqual(room.phase, Phase.HAND_COMPLETE)
        self.assertIsNotNone(room.last_hand_summary)
        self.assertEqual(len(room.last_hand_summary.board), 5)
        self.assertEqual(sum(room.last_hand_summary.chip_deltas.values()), 0)

    def test_full_hand_runs_from_start_to_showdown_and_settlement(self) -> None:
        room = self.seated_heads_up_room()
        room.start_hand()
        room.seats[0].hole_cards = [c("ACE", "CLUBS"), c("KING", "DIAMONDS")]
        room.seats[1].hole_cards = [c("QUEEN", "HEARTS"), c("JACK", "HEARTS")]
        room.deck = [
            c("TWO", "CLUBS"),
            c("SEVEN", "DIAMONDS"),
            c("NINE", "HEARTS"),
            c("JACK", "SPADES"),
            c("QUEEN", "CLUBS"),
        ]

        self.act_current(room, "CALL")
        self.act_current(room, "CHECK")
        self.assertEqual(room.phase, Phase.FLOP)

        self.act_current(room, "CHECK")
        self.act_current(room, "CHECK")
        self.assertEqual(room.phase, Phase.TURN)

        self.act_current(room, "CHECK")
        self.act_current(room, "CHECK")
        self.assertEqual(room.phase, Phase.RIVER)

        self.act_current(room, "CHECK")
        self.act_current(room, "CHECK")

        self.assertEqual(room.phase, Phase.HAND_COMPLETE)
        self.assertEqual(room.pot, 0)
        self.assertIsNotNone(room.last_hand_summary)
        self.assertEqual(room.last_hand_summary.winner_seats, (1,))
        self.assertEqual(room.last_hand_summary.hand_names[1], "Two Pair")
        self.assertEqual(sum(room.last_hand_summary.chip_deltas.values()), 0)

    def test_start_countdown_enters_hand_after_deadline(self) -> None:
        room = self.seated_heads_up_room()
        room.request_start("p1", now=100.0)

        changed = room.update(105.1)

        self.assertTrue(changed)
        self.assertEqual(room.phase, Phase.PREFLOP)
        self.assertTrue(room.current_hand_id)
        self.assertEqual(room.hand_number, 1)
        self.assertEqual(room.room_status, RoomStatus.PLAYING)

    def test_hand_complete_resets_table_to_open_state(self) -> None:
        room = self.seated_heads_up_room()
        room.start_hand()
        room.player_move(room.seats[room.active_seat].player_id, "FOLD")

        self.assertEqual(room.phase, Phase.HAND_COMPLETE)

        room.update(room.hand_complete_at + 0.01)

        self.assertEqual(room.phase, Phase.WAITING)
        self.assertEqual(room.room_status, RoomStatus.OPEN)
        self.assertEqual(room.current_hand_id, "")
        self.assertEqual(room.pot, 0)
        self.assertEqual(room.board, [])
        self.assertEqual(room.seats[0].hole_cards, [])
        self.assertEqual(room.seats[1].hole_cards, [])

    def test_hand_logs_are_written_to_disk(self) -> None:
        with TemporaryDirectory() as temp_dir:
            logger = GameLogStore(temp_dir, "server", "test-room")
            room = PokerRoom("test", logger=logger, rng=random.Random(0))
            room.join("p1", "Alice")
            room.join("p2", "Bob")
            room.sit("p1", 0)
            room.sit("p2", 1)
            room.set_ready("p1", True)
            room.set_ready("p2", True)
            room.start_hand()

            room.player_move(room.seats[room.active_seat].player_id, "FOLD")

            hand_id = room.last_hand_summary.hand_id
            self.assertTrue(logger.room_log_path("test").exists())
            self.assertTrue(logger.hand_log_path("test", room.hand_number, hand_id).exists())

    def test_sit_uses_resolved_chip_balance(self) -> None:
        room = PokerRoom("test", chip_resolver=lambda _player_id, _name: 3456)
        room.join("p1", "Alice")

        room.sit("p1", 0)

        self.assertEqual(room.seats[0].chips, 3456)

    def test_stand_persists_player_balance(self) -> None:
        persisted: list[tuple[str, str, int]] = []
        room = PokerRoom("test", chip_persistor=lambda player_id, name, chips: persisted.append((player_id, name, chips)))
        room.join("p1", "Alice")
        room.sit("p1", 0)
        room.seats[0].chips = 2780

        room.stand("p1")

        self.assertEqual(persisted, [("p1", "Alice", 2780)])

    def test_finished_hand_persists_all_seated_balances(self) -> None:
        persisted: list[tuple[str, str, int]] = []
        room = PokerRoom("test", rng=random.Random(0), chip_persistor=lambda player_id, name, chips: persisted.append((player_id, name, chips)))
        room.join("p1", "Alice")
        room.join("p2", "Bob")
        room.sit("p1", 0)
        room.sit("p2", 1)
        room.set_ready("p1", True)
        room.set_ready("p2", True)
        room.start_hand()

        room.player_move(room.seats[room.active_seat].player_id, "FOLD")

        self.assertEqual(len(persisted), 2)
        self.assertEqual({row[0] for row in persisted}, {"p1", "p2"})


class PlayerChipStoreTest(unittest.TestCase):
    def test_store_creates_and_updates_balances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = PlayerChipStore(f"{temp_dir}/player_chips.json")

            created = store.get_or_create("Alice")
            updated = store.add_chips("Alice", 500)
            lowered = store.add_chips("Alice", -99999)

            self.assertEqual(created, 2000)
            self.assertEqual(updated, 2500)
            self.assertEqual(lowered, 0)


if __name__ == "__main__":
    unittest.main()
