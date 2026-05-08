from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

from shared.cards import Card


RANK_VALUES = {
    "TWO": 2,
    "THREE": 3,
    "FOUR": 4,
    "FIVE": 5,
    "SIX": 6,
    "SEVEN": 7,
    "EIGHT": 8,
    "NINE": 9,
    "TEN": 10,
    "JACK": 11,
    "QUEEN": 12,
    "KING": 13,
    "ACE": 14,
}

CATEGORY_NAMES = {
    8: "Straight Flush",
    7: "Four of a Kind",
    6: "Full House",
    5: "Flush",
    4: "Straight",
    3: "Three of a Kind",
    2: "Two Pair",
    1: "Pair",
    0: "High Card",
}


@dataclass(frozen=True, order=True)
class HandScore:
    category: int
    ranks: tuple[int, ...]


@dataclass(frozen=True)
class EvaluatedHand:
    score: HandScore
    cards: tuple[Card, ...]

    @property
    def name(self) -> str:
        return CATEGORY_NAMES[self.score.category]


def evaluate_best_hand(cards: Iterable[Card]) -> EvaluatedHand:
    available = tuple(cards)
    if len(available) < 5:
        raise ValueError("At least five cards are required")

    best: EvaluatedHand | None = None
    for candidate in combinations(available, 5):
        evaluated = EvaluatedHand(score_five_cards(candidate), tuple(candidate))
        if best is None or evaluated.score > best.score:
            best = evaluated

    if best is None:
        raise ValueError("No hand could be evaluated")
    return best


def score_five_cards(cards: Iterable[Card]) -> HandScore:
    hand = tuple(cards)
    if len(hand) != 5:
        raise ValueError("Exactly five cards are required")

    ranks = sorted((RANK_VALUES[card.rank] for card in hand), reverse=True)
    counts = {rank: ranks.count(rank) for rank in set(ranks)}
    groups = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    is_flush = len({card.suit for card in hand}) == 1
    straight_high = high_card_for_straight(ranks)

    if is_flush and straight_high:
        return HandScore(8, (straight_high,))

    if groups[0][1] == 4:
        quad = groups[0][0]
        kicker = max(rank for rank in ranks if rank != quad)
        return HandScore(7, (quad, kicker))

    if groups[0][1] == 3 and groups[1][1] == 2:
        return HandScore(6, (groups[0][0], groups[1][0]))

    if is_flush:
        return HandScore(5, tuple(ranks))

    if straight_high:
        return HandScore(4, (straight_high,))

    if groups[0][1] == 3:
        trips = groups[0][0]
        kickers = sorted((rank for rank in ranks if rank != trips), reverse=True)
        return HandScore(3, (trips, *kickers))

    pairs = sorted((rank for rank, count in counts.items() if count == 2), reverse=True)
    if len(pairs) == 2:
        kicker = max(rank for rank in ranks if rank not in pairs)
        return HandScore(2, (pairs[0], pairs[1], kicker))

    if len(pairs) == 1:
        pair = pairs[0]
        kickers = sorted((rank for rank in ranks if rank != pair), reverse=True)
        return HandScore(1, (pair, *kickers))

    return HandScore(0, tuple(ranks))


def high_card_for_straight(ranks: Iterable[int]) -> int:
    unique = sorted(set(ranks), reverse=True)
    if unique == [14, 5, 4, 3, 2]:
        return 5
    if len(unique) == 5 and unique[0] - unique[-1] == 4:
        return unique[0]
    return 0
