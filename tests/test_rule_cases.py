import random
import unittest

from shared.cards import Card
from shared.hand_evaluator import evaluate_best_hand
from shared.settlement import ShowdownPlayer, settle_showdown
from server.room import BIG_BLIND, Phase, PokerRoom


def c(rank: str, suit: str) -> Card:
    return Card(suit=suit, rank=rank)


class NaturalLanguageRuleCasesTest(unittest.TestCase):
    def seated_three_player_room(self) -> PokerRoom:
        room = PokerRoom("test", rng=random.Random(0))
        for index, name in enumerate(("Alice", "Bob", "Carol")):
            player_id = f"p{index}"
            room.join(player_id, name)
            room.sit(player_id, index)
            room.set_ready(player_id, True)
        return room

    def seated_heads_up_room(self) -> PokerRoom:
        room = PokerRoom("test", rng=random.Random(0))
        room.join("p1", "Alice")
        room.join("p2", "Bob")
        room.sit("p1", 0)
        room.sit("p2", 1)
        room.set_ready("p1", True)
        room.set_ready("p2", True)
        return room

    def current_player(self, room: PokerRoom) -> str:
        return room.seats[room.active_seat].player_id

    def test_rc01_cannot_start_hand_with_fewer_than_two_ready_players(self) -> None:
        """RC-01: 房间内少于两名准备玩家时不能开局。"""
        room = PokerRoom("test")
        room.join("p1", "Alice")
        room.sit("p1", 0)
        room.set_ready("p1", True)

        with self.assertRaisesRegex(ValueError, "At least two ready players are required"):
            room.start_hand()

    def test_rc02_heads_up_dealer_posts_small_blind_and_acts_first_preflop(self) -> None:
        """RC-02: 单挑时庄家下小盲并先行动。"""
        room = self.seated_heads_up_room()
        room.start_hand()

        self.assertIn(room.dealer_seat, (0, 1))
        other = 1 if room.dealer_seat == 0 else 0
        self.assertEqual(room.seats[room.dealer_seat].committed, 10)
        self.assertEqual(room.seats[other].committed, 20)
        self.assertEqual(room.active_seat, room.dealer_seat)

    def test_rc03_cannot_check_when_facing_a_bet(self) -> None:
        """RC-03: 面对未跟上的下注时不能过牌。"""
        room = self.seated_heads_up_room()
        room.start_hand()
        acting_player = self.current_player(room)

        with self.assertRaisesRegex(ValueError, "Cannot check facing a bet"):
            room.player_move(acting_player, "CHECK")

        self.assertEqual(room.phase, Phase.PREFLOP)
        self.assertEqual(room.seats[room.active_seat].player_id, acting_player)

    def test_rc04_raise_cannot_be_below_minimum_raise(self) -> None:
        """RC-04: 加注不能低于最小加注额。"""
        room = self.seated_heads_up_room()
        room.start_hand()

        with self.assertRaisesRegex(ValueError, "minimum"):
            room.player_move(self.current_player(room), "RAISE", 30)

        self.assertEqual(room.current_bet, BIG_BLIND)
        self.assertEqual(room.min_raise, BIG_BLIND)

    def test_rc06_last_live_player_wins_without_showdown(self) -> None:
        """RC-06: 其余玩家弃牌后应直接赢池。"""
        room = self.seated_heads_up_room()
        room.start_hand()
        loser = self.current_player(room)

        room.player_move(loser, "FOLD")

        self.assertEqual(room.phase, Phase.HAND_COMPLETE)
        self.assertEqual(len(room.last_hand_summary.winner_seats), 1)
        self.assertEqual(room.last_hand_summary.hand_names, {})
        self.assertEqual(room.pot, 0)

    def test_rc07_single_postflop_check_keeps_betting_round_open(self) -> None:
        """RC-07: 只有所有可行动玩家都行动后，牌局才进入下一街。"""
        room = self.seated_three_player_room()
        room.start_hand()

        room.player_move(self.current_player(room), "CALL")
        room.player_move(self.current_player(room), "CALL")
        room.player_move(self.current_player(room), "CHECK")
        self.assertEqual(room.phase, Phase.FLOP)

        first_actor = room.active_seat
        room.player_move(self.current_player(room), "CHECK")

        self.assertEqual(room.phase, Phase.FLOP)
        self.assertNotEqual(room.active_seat, first_actor)

    def test_rc08_best_five_cards_are_selected_from_seven(self) -> None:
        """RC-08: 摊牌时要从七张牌中自动选出最优五张。"""
        hand = evaluate_best_hand(
            [
                c("ACE", "SPADES"),
                c("KING", "SPADES"),
                c("QUEEN", "SPADES"),
                c("JACK", "SPADES"),
                c("TEN", "SPADES"),
                c("TWO", "CLUBS"),
                c("THREE", "DIAMONDS"),
            ]
        )

        self.assertEqual(hand.name, "Straight Flush")
        self.assertEqual(len(hand.cards), 5)
        self.assertEqual(hand.score.ranks, (14,))

    def test_rc09_wheel_straight_is_ranked_as_five_high(self) -> None:
        """RC-09: A-2-3-4-5 识别为轮顺。"""
        hand = evaluate_best_hand(
            [
                c("ACE", "SPADES"),
                c("TWO", "HEARTS"),
                c("THREE", "DIAMONDS"),
                c("FOUR", "CLUBS"),
                c("FIVE", "SPADES"),
                c("KING", "HEARTS"),
                c("QUEEN", "CLUBS"),
            ]
        )

        self.assertEqual(hand.name, "Straight")
        self.assertEqual(hand.score.ranks, (5,))

    def test_rc10_kicker_breaks_tie_for_same_pair(self) -> None:
        """RC-10: 相同对子时由踢脚决定胜负。"""
        board = [
            c("ACE", "CLUBS"),
            c("ACE", "DIAMONDS"),
            c("NINE", "SPADES"),
            c("SEVEN", "HEARTS"),
            c("THREE", "CLUBS"),
        ]
        result = settle_showdown(
            [
                ShowdownPlayer(0, "Top kicker", (c("KING", "SPADES"), c("TWO", "HEARTS")), 100),
                ShowdownPlayer(1, "Lower kicker", (c("QUEEN", "SPADES"), c("JACK", "HEARTS")), 100),
            ],
            board,
        )

        self.assertEqual(result.awards[0].winner_seats, (0,))

    def test_rc11_side_pot_and_main_pot_are_awarded_to_eligible_players_only(self) -> None:
        """RC-11: 边池只能由有资格争夺该层筹码的玩家参与。"""
        board = [
            c("TWO", "CLUBS"),
            c("SEVEN", "DIAMONDS"),
            c("NINE", "HEARTS"),
            c("JACK", "SPADES"),
            c("QUEEN", "CLUBS"),
        ]
        result = settle_showdown(
            [
                ShowdownPlayer(0, "Short", (c("ACE", "CLUBS"), c("ACE", "DIAMONDS")), 100),
                ShowdownPlayer(1, "Mid", (c("KING", "CLUBS"), c("KING", "DIAMONDS")), 200),
                ShowdownPlayer(2, "Deep", (c("TWO", "HEARTS"), c("THREE", "HEARTS")), 200),
            ],
            board,
        )

        self.assertEqual(result.awards[0].amount, 300)
        self.assertEqual(result.awards[0].winner_seats, (0,))
        self.assertEqual(result.awards[0].eligible_seats, (0, 1, 2))
        self.assertEqual(result.awards[1].amount, 200)
        self.assertEqual(result.awards[1].winner_seats, (1,))
        self.assertEqual(result.awards[1].eligible_seats, (1, 2))

    def test_rc12_folded_player_keeps_contribution_but_cannot_win(self) -> None:
        """RC-12: 弃牌玩家保留贡献但不能赢池。"""
        board = [
            c("TWO", "CLUBS"),
            c("SEVEN", "DIAMONDS"),
            c("NINE", "HEARTS"),
            c("JACK", "SPADES"),
            c("QUEEN", "CLUBS"),
        ]
        result = settle_showdown(
            [
                ShowdownPlayer(0, "Folded", (c("ACE", "CLUBS"), c("ACE", "DIAMONDS")), 100, folded=True),
                ShowdownPlayer(1, "Caller", (c("KING", "CLUBS"), c("KING", "DIAMONDS")), 100),
            ],
            board,
        )

        self.assertEqual(result.awards[0].amount, 200)
        self.assertEqual(result.awards[0].winner_seats, (1,))
        self.assertEqual(result.winner_seats, (1,))

    def test_rc13_split_pot_keeps_total_chip_delta_balanced(self) -> None:
        """RC-13: 平分底池时总筹码变化必须守恒。"""
        room = self.seated_heads_up_room()
        room.start_hand()
        room.seats[0].hole_cards = [c("ACE", "CLUBS"), c("KING", "DIAMONDS")]
        room.seats[1].hole_cards = [c("ACE", "HEARTS"), c("KING", "SPADES")]
        room.board = [
            c("TWO", "CLUBS"),
            c("THREE", "DIAMONDS"),
            c("FOUR", "HEARTS"),
            c("FIVE", "SPADES"),
            c("NINE", "CLUBS"),
        ]
        room.phase = Phase.RIVER
        room.pot = room.seats[0].hand_committed + room.seats[1].hand_committed
        room.current_bet = 0
        room.seats[0].committed = 0
        room.seats[1].committed = 0
        room.seats[0].acted_this_round = False
        room.seats[1].acted_this_round = False
        room.active_seat = 0

        room.player_move("p1", "CHECK")
        room.player_move("p2", "CHECK")

        self.assertEqual(room.phase, Phase.HAND_COMPLETE)
        self.assertIsNotNone(room.last_hand_summary)
        self.assertEqual(room.last_hand_summary.winner_seats, (0, 1))
        self.assertEqual(sum(room.last_hand_summary.chip_deltas.values()), 0)
        self.assertEqual(room.seats[0].chips, room.seats[1].chips)

    def test_rc05_short_all_in_does_not_reduce_min_raise(self) -> None:
        """RC-05: 短码全下提高跟注线，但不会形成完整加注。"""
        room = self.seated_three_player_room()
        room.start_hand()
        current_actor = room.seats[room.active_seat]
        current_actor.chips = 25

        room.player_move(current_actor.player_id, "ALL_IN")

        self.assertEqual(room.current_bet, 25)
        self.assertEqual(room.min_raise, BIG_BLIND)
        self.assertTrue(current_actor.all_in)


if __name__ == "__main__":
    unittest.main()
