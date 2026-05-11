from __future__ import annotations

from dataclasses import dataclass

from src.shared.cards import Card
from src.shared.hand_evaluator import EvaluatedHand, evaluate_best_hand


@dataclass(frozen=True)
class ShowdownPlayer:
    seat_index: int
    name: str
    hole_cards: tuple[Card, ...]
    contribution: int
    folded: bool = False


@dataclass(frozen=True)
class PotAward:
    amount: int
    winner_seats: tuple[int, ...]
    eligible_seats: tuple[int, ...]


@dataclass(frozen=True)
class ShowdownResult:
    awards: tuple[PotAward, ...]
    hands: dict[int, EvaluatedHand]

    @property
    def winner_seats(self) -> tuple[int, ...]:
        winners: list[int] = []
        for award in self.awards:
            for seat_index in award.winner_seats:
                if seat_index not in winners:
                    winners.append(seat_index)
        return tuple(winners)


def settle_showdown(players: list[ShowdownPlayer], board: list[Card]) -> ShowdownResult:
    if len(board) < 5:
        raise ValueError("Showdown requires five board cards")

    hands = {
        player.seat_index: evaluate_best_hand((*player.hole_cards, *board))
        for player in players
        if not player.folded and len(player.hole_cards) == 2
    }
    if not hands:
        raise ValueError("No live hands can win the pot")

    awards: list[PotAward] = []
    previous_level = 0
    for level in sorted({player.contribution for player in players if player.contribution > 0}):
        contributors = [player for player in players if player.contribution >= level]
        pot_amount = (level - previous_level) * len(contributors)
        previous_level = level
        if pot_amount <= 0:
            continue

        eligible = [player for player in contributors if not player.folded and player.seat_index in hands]
        if not eligible:
            continue

        best_score = max(hands[player.seat_index].score for player in eligible)
        winners = tuple(
            player.seat_index for player in eligible if hands[player.seat_index].score == best_score
        )
        awards.append(PotAward(pot_amount, winners, tuple(player.seat_index for player in eligible)))

    return ShowdownResult(tuple(awards), hands)
