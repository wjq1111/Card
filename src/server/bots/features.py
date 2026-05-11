from __future__ import annotations

from collections import Counter
import random

from src.server.bots.equity import estimate_equity
from src.server.bots.models import BotFeatures, BotObservation, BotProfile
from src.shared.cards import Card
from src.shared.hand_evaluator import RANK_VALUES, evaluate_best_hand


RANK_ORDER = tuple(RANK_VALUES)
LOW_ACE_RUN = (14, 2, 3, 4, 5)
STRAIGHT_RUNS = (LOW_ACE_RUN,) + tuple(tuple(range(start, start + 5)) for start in range(2, 11))


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def extract_features(
    observation: BotObservation,
    profile: BotProfile | None = None,
    rng: random.Random | None = None,
) -> BotFeatures:
    profile = profile or BotProfile()
    made = made_strength(observation, profile)
    draw = draw_strength(observation)
    equity = estimate_equity(observation, rng=rng)
    pot_odds = pot_odds_fit(observation, made, draw, equity)
    position = position_score(observation)
    pressure = pressure_score(observation)
    spr = spr_score(observation)
    wetness = board_wetness(observation.board_cards)
    opponent_vpip = opponent_vpip_score(observation)
    opponent_pfr = opponent_pfr_score(observation)
    opponent_aggression = opponent_aggression_score(observation)
    opponent_fold_to_raise = opponent_fold_to_raise_score(observation)
    recent_raise_pressure = recent_raise_pressure_score(observation)
    return BotFeatures(
        made_strength=made,
        draw_strength=draw,
        equity=equity,
        pot_odds_fit=pot_odds,
        position_score=position,
        pressure_score=pressure,
        spr_score=spr,
        board_wetness=wetness,
        opponent_vpip=opponent_vpip,
        opponent_pfr=opponent_pfr,
        opponent_aggression=opponent_aggression,
        opponent_fold_to_raise=opponent_fold_to_raise,
        recent_raise_pressure=recent_raise_pressure,
    )


def made_strength(observation: BotObservation, profile: BotProfile) -> float:
    if observation.phase == "PREFLOP" or len(observation.board_cards) < 3:
        base = preflop_strength(observation.hole_cards)
        base += (position_score(observation) - 0.5) * 0.12
        base += (profile.looseness - 0.5) * 0.10
        return clamp(base)

    cards = tuple(observation.hole_cards) + tuple(observation.board_cards)
    if len(cards) < 5:
        return preflop_strength(observation.hole_cards)

    hand = evaluate_best_hand(cards)
    category_base = {
        0: 0.12,
        1: 0.35,
        2: 0.58,
        3: 0.70,
        4: 0.78,
        5: 0.82,
        6: 0.90,
        7: 0.97,
        8: 1.00,
    }[hand.score.category]
    if hand.score.category == 1:
        pair_rank = hand.score.ranks[0]
        category_base = 0.25 + pair_rank / 14 * 0.20
    return clamp(category_base)


def preflop_strength(cards: tuple[Card, ...]) -> float:
    if len(cards) != 2:
        return 0.0

    first, second = cards
    first_rank = RANK_VALUES[first.rank]
    second_rank = RANK_VALUES[second.rank]
    high = max(first_rank, second_rank)
    low = min(first_rank, second_rank)
    suited = first.suit == second.suit

    if first_rank == second_rank:
        if high == 14:
            return 1.00
        if high == 13:
            return 0.96
        if high == 12:
            return 0.92
        if high == 11:
            return 0.86
        if high == 10:
            return 0.80
        if high >= 7:
            return 0.66
        return 0.50

    both_broadway = low >= 10
    has_ace = high == 14
    connector = high - low == 1

    if suited and both_broadway:
        return 0.72
    if both_broadway:
        return 0.62
    if suited and has_ace:
        return 0.64
    if has_ace and low >= 9:
        return 0.52
    if suited and connector and low >= 5:
        return 0.50
    if high >= 11 and low >= 9:
        return 0.48
    return 0.25


def draw_strength(observation: BotObservation) -> float:
    if observation.phase == "RIVER":
        return 0.0

    cards = tuple(observation.hole_cards) + tuple(observation.board_cards)
    if len(observation.board_cards) < 3:
        return 0.0

    score = 0.0
    suit_counts = Counter(card.suit for card in cards)
    if suit_counts and max(suit_counts.values()) == 4:
        score += 0.35

    ranks = {RANK_VALUES[card.rank] for card in cards}
    straight_draw = straight_draw_score(ranks)
    score += straight_draw

    board_ranks = [RANK_VALUES[card.rank] for card in observation.board_cards]
    hole_ranks = [RANK_VALUES[card.rank] for card in observation.hole_cards]
    if board_ranks and len(hole_ranks) == 2 and all(rank > max(board_ranks) for rank in hole_ranks):
        score += 0.10

    if observation.phase == "TURN":
        score *= 0.75
    return clamp(score)


def straight_draw_score(ranks: set[int]) -> float:
    best = 0.0
    for run in STRAIGHT_RUNS:
        present = {rank for rank in run if rank in ranks}
        if len(present) != 4:
            continue
        missing = next(rank for rank in run if rank not in ranks)
        if run == LOW_ACE_RUN or missing in (run[0], run[-1]):
            best = max(best, 0.30)
        else:
            best = max(best, 0.14)
    return best


def pot_odds_fit(observation: BotObservation, made: float, draw: float, equity: float) -> float:
    if observation.to_call <= 0:
        return 1.0
    pot_after_call = observation.pot + observation.to_call
    pot_odds = observation.to_call / max(1, pot_after_call)
    estimated_equity = max(equity, made * 0.55 + draw * 0.45)
    return clamp((estimated_equity - pot_odds + 0.25) / 0.50)


def position_score(observation: BotObservation) -> float:
    if observation.live_player_count <= 2:
        return 0.75 if observation.seat_index == observation.dealer_seat else 0.35
    if observation.seat_count <= 1 or observation.dealer_seat < 0:
        return 0.45
    distance_from_dealer = (observation.seat_index - observation.dealer_seat) % observation.seat_count
    relative = distance_from_dealer / max(1, observation.seat_count - 1)
    return clamp(0.30 + relative * 0.40)


def pressure_score(observation: BotObservation) -> float:
    stack_basis = max(1, observation.chips + observation.committed)
    return clamp((observation.to_call / stack_basis) * 2.5)


def spr_score(observation: BotObservation) -> float:
    spr = observation.stack_after_call / max(1, observation.pot + observation.to_call)
    return clamp(spr / 10)


def board_wetness(board_cards: tuple[Card, ...]) -> float:
    if len(board_cards) < 3:
        return 0.0
    score = 0.0
    suits = Counter(card.suit for card in board_cards)
    if max(suits.values()) >= 3:
        score += 0.35

    ranks = sorted({RANK_VALUES[card.rank] for card in board_cards})
    for run in STRAIGHT_RUNS:
        if len({rank for rank in run if rank in ranks}) >= 3:
            score += 0.30
            break

    rank_counts = Counter(RANK_VALUES[card.rank] for card in board_cards)
    if any(count >= 2 for count in rank_counts.values()):
        score += 0.15
    return clamp(score)


def opponent_vpip_score(observation: BotObservation) -> float:
    return weighted_opponent_average(observation, lambda opponent: opponent.vpip_rate)


def opponent_pfr_score(observation: BotObservation) -> float:
    return weighted_opponent_average(observation, lambda opponent: opponent.pfr_rate)


def opponent_aggression_score(observation: BotObservation) -> float:
    return weighted_opponent_average(observation, lambda opponent: clamp(opponent.aggression_factor / 3.0))


def opponent_fold_to_raise_score(observation: BotObservation) -> float:
    return weighted_opponent_average(observation, lambda opponent: opponent.fold_to_raise_rate)


def recent_raise_pressure_score(observation: BotObservation) -> float:
    active_opponents = [opponent for opponent in observation.opponents if not opponent.folded]
    if not active_opponents:
        return 0.0
    score = 0.0
    total_weight = 0.0
    for opponent in active_opponents:
        weight = opponent_pressure_weight(observation, opponent)
        score += weight * opponent.recent_raise_rate * 0.6
        if opponent.last_action in {"RAISE", "ALL_IN"}:
            score += weight * 0.4
        total_weight += weight
    return clamp(score / max(1.0, total_weight))


def weighted_opponent_average(
    observation: BotObservation,
    value_getter,
) -> float:
    active_opponents = [opponent for opponent in observation.opponents if not opponent.folded]
    if not active_opponents:
        return 0.0
    weighted_sum = 0.0
    total_weight = 0.0
    for opponent in active_opponents:
        weight = opponent_pressure_weight(observation, opponent)
        weighted_sum += weight * clamp(value_getter(opponent))
        total_weight += weight
    return clamp(weighted_sum / max(1.0, total_weight))


def opponent_pressure_weight(observation: BotObservation, opponent) -> float:
    weight = 1.0
    if opponent.all_in:
        weight += 0.15
    if observation.to_call > 0:
        pressure_share = max(0, opponent.committed - observation.committed) / max(1, observation.to_call)
        weight += clamp(pressure_share, 0.0, 2.0) * 1.2
        if opponent.committed == observation.current_bet:
            weight += 0.8
        if opponent.last_action_phase == observation.phase and opponent.last_action in {"RAISE", "ALL_IN"}:
            weight += 1.6
    elif opponent.last_action_phase == observation.phase and opponent.last_action in {"RAISE", "ALL_IN"}:
        weight += 0.6
    return weight
