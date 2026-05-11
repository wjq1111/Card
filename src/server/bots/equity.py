from __future__ import annotations

import random

from src.server.bots.models import BotObservation
from src.shared.cards import Card, RANKS, SUITS
from src.shared.hand_evaluator import evaluate_best_hand


DEFAULT_MONTE_CARLO_SAMPLES = {
    "PREFLOP": 40,
    "FLOP": 32,
    "TURN": 24,
    "RIVER": 20,
}


def estimate_equity(
    observation: BotObservation,
    rng: random.Random | None = None,
    *,
    samples: int | None = None,
) -> float:
    if observation.live_player_count <= 1:
        return 1.0

    known_cards = tuple(observation.hole_cards) + tuple(observation.board_cards)
    remaining_board_cards = max(0, 5 - len(observation.board_cards))
    opponent_count = max(1, observation.live_player_count - 1)
    cards_needed = remaining_board_cards + opponent_count * 2
    if cards_needed <= 0:
        return showdown_equity(observation.hole_cards, observation.board_cards, ())

    deck = available_cards(known_cards)
    if len(deck) < cards_needed:
        return 0.0

    rng = rng or random.Random()
    total_equity = 0.0
    trial_count = max(1, samples or default_sample_count(observation))
    for _ in range(trial_count):
        sample = rng.sample(deck, cards_needed)
        board = tuple(observation.board_cards) + tuple(sample[:remaining_board_cards])
        opponents: list[tuple[Card, Card]] = []
        cursor = remaining_board_cards
        for _ in range(opponent_count):
            opponents.append((sample[cursor], sample[cursor + 1]))
            cursor += 2
        total_equity += showdown_equity(observation.hole_cards, board, tuple(opponents))
    return total_equity / trial_count


def default_sample_count(observation: BotObservation) -> int:
    return DEFAULT_MONTE_CARLO_SAMPLES.get(observation.phase, 24)


def available_cards(known_cards: tuple[Card, ...]) -> list[Card]:
    known = set(known_cards)
    return [Card(suit=suit, rank=rank) for suit in SUITS for rank in RANKS if Card(suit=suit, rank=rank) not in known]


def showdown_equity(
    hero_hole_cards: tuple[Card, ...],
    board_cards: tuple[Card, ...],
    opponent_hole_cards: tuple[tuple[Card, Card], ...],
) -> float:
    hero_hand = evaluate_best_hand(tuple(hero_hole_cards) + tuple(board_cards))
    winner_count = 1
    hero_best = True

    for opponent_cards in opponent_hole_cards:
        opponent_hand = evaluate_best_hand(tuple(opponent_cards) + tuple(board_cards))
        if opponent_hand.score > hero_hand.score:
            hero_best = False
            winner_count = 0
        elif opponent_hand.score == hero_hand.score:
            winner_count += 1

    if not hero_best:
        return 0.0
    return 1.0 / winner_count
