import unittest

from src.shared.cards import Card
from src.shared.settlement import ShowdownPlayer, settle_showdown


def c(rank: str, suit: str) -> Card:
    return Card(suit=suit, rank=rank)


class SettlementTest(unittest.TestCase):
    def test_side_pot_only_includes_eligible_players(self) -> None:
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
        self.assertEqual(result.awards[1].amount, 200)
        self.assertEqual(result.awards[1].winner_seats, (1,))

    def test_folded_player_contributes_but_cannot_win(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
