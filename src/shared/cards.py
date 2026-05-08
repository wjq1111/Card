from __future__ import annotations

from dataclasses import dataclass
import random


SUITS = ("CLUBS", "DIAMONDS", "HEARTS", "SPADES")
RANKS = ("TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN", "JACK", "QUEEN", "KING", "ACE")


@dataclass(frozen=True)
class Card:
    suit: str
    rank: str


def shuffled_deck(rng: random.Random | None = None) -> list[Card]:
    deck = [Card(suit=suit, rank=rank) for suit in SUITS for rank in RANKS]
    (rng or random).shuffle(deck)
    return deck
