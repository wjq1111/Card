import unittest

from src.shared.cards import Card
from src.shared.hand_evaluator import evaluate_best_hand


def c(rank: str, suit: str = "SPADES") -> Card:
    return Card(suit=suit, rank=rank)


class HandEvaluatorTest(unittest.TestCase):
    def test_selects_best_five_from_seven_cards(self) -> None:
        hand = evaluate_best_hand(
            [
                c("ACE", "HEARTS"),
                c("KING", "HEARTS"),
                c("QUEEN", "HEARTS"),
                c("JACK", "HEARTS"),
                c("TEN", "HEARTS"),
                c("TWO", "CLUBS"),
                c("TWO", "DIAMONDS"),
            ]
        )

        self.assertEqual(hand.name, "Straight Flush")
        self.assertEqual(hand.score.ranks, (14,))

    def test_handles_wheel_straight(self) -> None:
        hand = evaluate_best_hand(
            [
                c("ACE", "CLUBS"),
                c("TWO", "DIAMONDS"),
                c("THREE", "SPADES"),
                c("FOUR", "HEARTS"),
                c("FIVE", "CLUBS"),
                c("KING", "DIAMONDS"),
                c("NINE", "SPADES"),
            ]
        )

        self.assertEqual(hand.name, "Straight")
        self.assertEqual(hand.score.ranks, (5,))

    def test_pair_kickers_break_ties(self) -> None:
        ace_kicker = evaluate_best_hand(
            [
                c("KING", "CLUBS"),
                c("KING", "DIAMONDS"),
                c("ACE", "SPADES"),
                c("NINE", "HEARTS"),
                c("EIGHT", "CLUBS"),
            ]
        )
        queen_kicker = evaluate_best_hand(
            [
                c("KING", "HEARTS"),
                c("KING", "SPADES"),
                c("QUEEN", "CLUBS"),
                c("NINE", "DIAMONDS"),
                c("EIGHT", "HEARTS"),
            ]
        )

        self.assertGreater(ace_kicker.score, queen_kicker.score)


if __name__ == "__main__":
    unittest.main()
