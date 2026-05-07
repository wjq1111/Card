import unittest
from tempfile import TemporaryDirectory

from shared.cards import Card
from shared.game_logging import GameLogStore
from server.room import Phase, PokerRoom


def c(rank: str, suit: str) -> Card:
    return Card(suit=suit, rank=rank)


class RoomRulesTest(unittest.TestCase):
    def seated_heads_up_room(self) -> PokerRoom:
        room = PokerRoom("test")
        room.join("p1", "Alice")
        room.join("p2", "Bob")
        room.sit("p1", 0)
        room.sit("p2", 1)
        room.set_ready("p1", True)
        room.set_ready("p2", True)
        return room

    def test_heads_up_dealer_posts_small_blind_and_acts_preflop(self) -> None:
        room = self.seated_heads_up_room()
        room.start_hand()

        self.assertEqual(room.dealer_seat, 0)
        self.assertEqual(room.seats[0].committed, 10)
        self.assertEqual(room.seats[1].committed, 20)
        self.assertEqual(room.active_seat, 0)

    def test_postflop_check_does_not_end_round_until_everyone_acts(self) -> None:
        room = self.seated_heads_up_room()
        room.start_hand()

        room.player_move("p1", "CALL")
        room.player_move("p2", "CHECK")
        self.assertEqual(room.phase, Phase.FLOP)

        room.player_move("p2", "CHECK")

        self.assertEqual(room.phase, Phase.FLOP)
        self.assertEqual(room.active_seat, 0)

    def test_uncontested_pot_is_awarded_when_everyone_else_folds(self) -> None:
        room = self.seated_heads_up_room()
        room.start_hand()
        pot = room.pot

        room.player_move("p1", "FOLD")

        self.assertEqual(room.phase, Phase.HAND_COMPLETE)
        self.assertEqual(room.pot, 0)
        self.assertEqual(room.seats[1].chips, 2000 - 20 + pot)
        self.assertIsNotNone(room.last_hand_summary)
        self.assertEqual(room.last_hand_summary.winner_seats, (1,))

    def test_raise_below_minimum_is_rejected(self) -> None:
        room = self.seated_heads_up_room()
        room.start_hand()

        with self.assertRaisesRegex(ValueError, "minimum"):
            room.player_move("p1", "RAISE", 30)

    def test_short_all_in_updates_call_amount_without_full_raise(self) -> None:
        room = PokerRoom("test")
        for index in range(3):
            player_id = f"p{index}"
            room.join(player_id, f"Player {index}")
            room.sit(player_id, index)
            room.set_ready(player_id, True)
        room.start_hand()
        room.seats[0].chips = 25

        room.player_move("p0", "ALL_IN")

        self.assertEqual(room.current_bet, 25)
        self.assertEqual(room.min_raise, 20)
        self.assertTrue(room.seats[0].acted_this_round)

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

        room.player_move("p1", "CALL")
        room.player_move("p2", "CHECK")
        room.player_move("p2", "CHECK")
        room.player_move("p1", "CHECK")
        room.player_move("p2", "CHECK")
        room.player_move("p1", "CHECK")
        room.player_move("p2", "CHECK")
        room.player_move("p1", "CHECK")

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

        room.player_move("p1", "CALL")
        room.player_move("p2", "CHECK")
        self.assertEqual(room.phase, Phase.FLOP)

        room.player_move("p2", "CHECK")
        room.player_move("p1", "CHECK")
        self.assertEqual(room.phase, Phase.TURN)

        room.player_move("p2", "CHECK")
        room.player_move("p1", "CHECK")
        self.assertEqual(room.phase, Phase.RIVER)

        room.player_move("p2", "CHECK")
        room.player_move("p1", "CHECK")

        self.assertEqual(room.phase, Phase.HAND_COMPLETE)
        self.assertEqual(room.pot, 0)
        self.assertIsNotNone(room.last_hand_summary)
        self.assertEqual(room.last_hand_summary.winner_seats, (1,))
        self.assertEqual(room.last_hand_summary.hand_names[1], "Two Pair")
        self.assertEqual(room.seats[0].chips, 1980)
        self.assertEqual(room.seats[1].chips, 2020)
        self.assertEqual(sum(room.last_hand_summary.chip_deltas.values()), 0)

    def test_ready_players_auto_start_after_countdown(self) -> None:
        room = self.seated_heads_up_room()

        changed = room.update(100.0)

        self.assertTrue(changed)
        self.assertEqual(room.phase, Phase.WAITING)
        self.assertEqual(room.countdown_seconds_remaining(100.0), 3)

        room.update(103.1)

        self.assertEqual(room.phase, Phase.PREFLOP)
        self.assertTrue(room.current_hand_id)
        self.assertEqual(room.hand_number, 1)

    def test_hand_complete_resets_table_and_can_schedule_next_hand(self) -> None:
        room = self.seated_heads_up_room()
        room.start_hand()

        first_hand_id = room.current_hand_id
        room.player_move("p1", "FOLD")

        self.assertEqual(room.phase, Phase.HAND_COMPLETE)
        self.assertEqual(room.current_hand_id, first_hand_id)

        room.update(room.hand_complete_at + 0.01)

        self.assertEqual(room.phase, Phase.WAITING)
        self.assertEqual(room.current_hand_id, "")
        self.assertEqual(room.pot, 0)
        self.assertEqual(room.board, [])
        self.assertEqual(room.seats[0].hole_cards, [])
        self.assertEqual(room.seats[1].hole_cards, [])
        self.assertIsNotNone(room.countdown_deadline_at)

    def test_hand_logs_are_written_to_disk(self) -> None:
        with TemporaryDirectory() as temp_dir:
            logger = GameLogStore(temp_dir, "server", "test-room")
            room = PokerRoom("test", logger=logger)
            room.join("p1", "Alice")
            room.join("p2", "Bob")
            room.sit("p1", 0)
            room.sit("p2", 1)
            room.set_ready("p1", True)
            room.set_ready("p2", True)
            room.start_hand()

            room.player_move("p1", "FOLD")

            hand_id = room.last_hand_summary.hand_id
            self.assertTrue(logger.room_log_path("test").exists())
            self.assertTrue(logger.hand_log_path("test", room.hand_number, hand_id).exists())


if __name__ == "__main__":
    unittest.main()
