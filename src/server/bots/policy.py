from __future__ import annotations

import random

from src.server.bots.features import clamp, extract_features
from src.server.bots.models import ActionCandidate, ActionScore, BotDecision, BotFeatures, BotObservation, BotProfile, ScoreWeights

BET_ROUNDING_UNIT = 10


def decide_action(
    observation: BotObservation,
    profile: BotProfile | None = None,
    weights: ScoreWeights | None = None,
    rng: random.Random | None = None,
) -> BotDecision:
    profile = profile or BotProfile()
    weights = weights or ScoreWeights()
    rng = rng or random.Random()
    features = extract_features(observation, profile, rng=rng)
    candidates = legal_candidates(observation)
    if not candidates:
        return BotDecision("CHECK", reason="No candidate actions were available", features=features)

    scores = tuple(score_candidate(candidate, observation, features, profile, weights, rng) for candidate in candidates)
    best = max(scores, key=lambda item: item.score)
    reason = f"{best.move_type} won weighted scoring"
    return BotDecision(best.move_type, best.amount, reason=reason, features=features, scores=scores)


def legal_candidates(observation: BotObservation) -> tuple[ActionCandidate, ...]:
    candidates: list[ActionCandidate] = []
    legal = set(observation.legal_actions)

    if "FOLD" in legal:
        candidates.append(ActionCandidate("FOLD"))
    if "CHECK" in legal:
        candidates.append(ActionCandidate("CHECK"))
    if "CALL" in legal:
        candidates.append(ActionCandidate("CALL"))

    if "RAISE" in legal:
        for target in raise_targets(observation):
            if observation.minimum_raise_to <= target < observation.maximum_raise_to:
                candidate = ActionCandidate("RAISE", target)
                if candidate not in candidates:
                    candidates.append(candidate)

    if "ALL_IN" in legal:
        candidates.append(ActionCandidate("ALL_IN"))

    return tuple(candidates)


def raise_targets(observation: BotObservation) -> tuple[int, ...]:
    if observation.phase == "PREFLOP":
        raw_targets = preflop_raise_targets(observation)
    else:
        raw_targets = tuple(
            observation.committed + observation.to_call + round(observation.pot * ratio)
            for ratio in (0.33, 0.50, 0.75)
        )

    normalized: list[int] = []
    for target in raw_targets:
        rounded = normalize_raise_target(observation, target)
        if observation.minimum_raise_to <= rounded < observation.maximum_raise_to and rounded not in normalized:
            normalized.append(rounded)
    return tuple(normalized)


def preflop_raise_targets(observation: BotObservation) -> tuple[int, ...]:
    spot = classify_preflop_spot(observation)
    if spot == "SHORT_STACK_JAM":
        return ()
    if spot == "UNOPENED":
        return (
            observation.current_bet + round(observation.min_raise * 1.5),
            observation.current_bet + round(observation.min_raise * 2.0),
            observation.current_bet + round(observation.min_raise * 3.0),
        )
    if spot == "FACING_3BET":
        return (
            observation.current_bet + observation.min_raise * 2,
            observation.current_bet + observation.min_raise * 4,
        )
    return (
        observation.current_bet + observation.min_raise * 2,
        observation.current_bet + observation.min_raise * 3,
        observation.current_bet + observation.min_raise * 4,
    )


def normalize_raise_target(observation: BotObservation, target: int) -> int:
    bounded = max(observation.minimum_raise_to, min(target, observation.maximum_raise_to))
    rounded = int(round(bounded / BET_ROUNDING_UNIT) * BET_ROUNDING_UNIT)
    if rounded < observation.minimum_raise_to:
        rounded = ((observation.minimum_raise_to + BET_ROUNDING_UNIT - 1) // BET_ROUNDING_UNIT) * BET_ROUNDING_UNIT
    if rounded >= observation.maximum_raise_to:
        rounded = ((observation.maximum_raise_to - 1) // BET_ROUNDING_UNIT) * BET_ROUNDING_UNIT
    if rounded < observation.minimum_raise_to:
        return observation.minimum_raise_to
    return rounded


def raise_target_for_ratio(observation: BotObservation, ratio: float) -> int:
    target = observation.committed + observation.to_call + round(observation.pot * ratio)
    return normalize_raise_target(observation, target)


def score_candidate(
    candidate: ActionCandidate,
    observation: BotObservation,
    features: BotFeatures,
    profile: BotProfile,
    weights: ScoreWeights,
    rng: random.Random,
) -> ActionScore:
    if candidate.move_type == "CHECK":
        score = score_check(features, profile, weights)
    elif candidate.move_type == "CALL":
        score = score_call(features, profile, weights)
    elif candidate.move_type == "FOLD":
        score = score_fold(features, profile, weights)
    elif candidate.move_type == "RAISE":
        score = score_raise(candidate, observation, features, profile, weights)
    elif candidate.move_type == "ALL_IN":
        score = score_all_in(features, profile, weights)
    else:
        score = -1.0

    if observation.phase == "PREFLOP":
        score += preflop_candidate_adjustment(candidate, observation, features, profile)

    if profile.randomness > 0:
        score += rng.uniform(-profile.randomness, profile.randomness)
    return ActionScore(candidate.move_type, candidate.amount, score)


def score_check(features: BotFeatures, profile: BotProfile, weights: ScoreWeights) -> float:
    return (
        weights.check_made_strength * features.made_strength
        + weights.check_draw_strength * features.draw_strength
        + weights.check_equity * features.equity
        + weights.check_position_score * features.position_score
        + weights.check_board_wetness * features.board_wetness
        + weights.check_passive_bias * (1 - profile.aggression)
    )


def score_call(features: BotFeatures, profile: BotProfile, weights: ScoreWeights) -> float:
    return (
        weights.call_made_strength * features.made_strength
        + weights.call_draw_strength * features.draw_strength
        + weights.call_equity * features.equity
        + weights.call_pot_odds_fit * features.pot_odds_fit
        + weights.call_looseness * profile.looseness
        + weights.call_pressure_score * features.pressure_score
        + weights.call_risk_tolerance * profile.risk_tolerance
        + weights.call_opponent_aggression * features.opponent_aggression
    )


def score_fold(features: BotFeatures, profile: BotProfile, weights: ScoreWeights) -> float:
    return (
        weights.fold_pressure_score * features.pressure_score
        + weights.fold_weak_made * (1 - features.made_strength)
        + weights.fold_weak_draw * (1 - features.draw_strength)
        + weights.fold_equity * features.equity
        + weights.fold_pot_odds_fit * features.pot_odds_fit
        + weights.fold_looseness * profile.looseness
        + weights.fold_recent_raise_pressure * features.recent_raise_pressure
    )


def score_raise(
    candidate: ActionCandidate,
    observation: BotObservation,
    features: BotFeatures,
    profile: BotProfile,
    weights: ScoreWeights,
) -> float:
    value_raise = (
        weights.raise_value_made_strength * features.made_strength
        + weights.raise_value_board_wetness * features.board_wetness
    )
    semi_bluff_raise = (
        weights.raise_bluff_draw_strength * features.draw_strength
        + weights.raise_bluff_position_score * features.position_score
        + weights.raise_bluff_board_wetness * features.board_wetness
    )
    raise_extra = max(0, candidate.amount - observation.committed - observation.to_call)
    raise_size_risk = raise_extra / max(1, observation.chips + observation.committed)
    return (
        value_raise
        + semi_bluff_raise
        + weights.raise_equity * features.equity
        + weights.raise_opponent_fold_to_raise * features.opponent_fold_to_raise
        + weights.raise_opponent_vpip * features.opponent_vpip
        + weights.raise_aggression * profile.aggression
        + weights.raise_bluff_rate * profile.bluff_rate
        + weights.raise_pressure_score * features.pressure_score
        + weights.raise_size_risk * clamp(raise_size_risk)
    )


def score_all_in(features: BotFeatures, profile: BotProfile, weights: ScoreWeights) -> float:
    score = (
        weights.all_in_made_strength * features.made_strength
        + weights.all_in_draw_strength * features.draw_strength
        + weights.all_in_equity * features.equity
        + weights.all_in_low_spr * (1 - features.spr_score)
        + weights.all_in_risk_tolerance * profile.risk_tolerance
        + weights.all_in_aggression * profile.aggression
        + weights.all_in_bad_pot_odds * (1 - features.pot_odds_fit)
    )
    if features.made_strength < weights.all_in_made_threshold and features.draw_strength < weights.all_in_draw_threshold:
        score += weights.all_in_weak_penalty
    return score


def classify_preflop_spot(observation: BotObservation) -> str:
    effective_stack = observation.committed + observation.chips
    aggressive_opponents = [
        opponent
        for opponent in observation.opponents
        if not opponent.folded
        and opponent.last_action_phase == "PREFLOP"
        and opponent.last_action in {"RAISE", "ALL_IN"}
    ]
    if observation.to_call > 0 and (
        observation.to_call / max(1, effective_stack) >= 0.33 or effective_stack <= observation.min_raise * 12
    ):
        return "SHORT_STACK_JAM"
    if observation.current_bet <= observation.min_raise and observation.to_call <= observation.min_raise:
        return "UNOPENED"
    if len(aggressive_opponents) >= 2 or observation.current_bet >= observation.min_raise * 5:
        return "FACING_3BET"
    return "FACING_OPEN"


def preflop_candidate_adjustment(
    candidate: ActionCandidate,
    observation: BotObservation,
    features: BotFeatures,
    profile: BotProfile,
) -> float:
    spot = classify_preflop_spot(observation)
    equity = features.equity
    short_stack = observation.committed + observation.chips <= observation.min_raise * 12

    if spot == "UNOPENED":
        if candidate.move_type == "RAISE":
            return max(0.0, equity - 0.45) * 0.75 + features.position_score * 0.08 + profile.aggression * 0.05
        if candidate.move_type == "CALL":
            return max(0.0, 0.10 - abs(equity - 0.44) * 0.45)
        if candidate.move_type == "FOLD":
            return max(0.0, 0.38 - equity) * 0.30
        if candidate.move_type == "CHECK":
            return max(0.0, 0.50 - equity) * 0.18
        if candidate.move_type == "ALL_IN":
            return max(0.0, equity - 0.78) * 0.20
        return 0.0

    if spot == "FACING_OPEN":
        if candidate.move_type == "RAISE":
            return max(0.0, equity - 0.58) * 0.95 + profile.aggression * 0.06
        if candidate.move_type == "CALL":
            return max(0.0, 0.18 - abs(equity - 0.55) * 0.90)
        if candidate.move_type == "FOLD":
            return max(0.0, 0.44 - equity) * 0.85
        if candidate.move_type == "ALL_IN":
            threshold = 0.56 if short_stack else 0.72
            scale = 0.75 if short_stack else 0.40
            return max(0.0, equity - threshold) * scale
        return 0.0

    if spot == "FACING_3BET":
        if equity < 0.56:
            if candidate.move_type == "FOLD":
                return 0.45 + features.recent_raise_pressure * 0.12
            if candidate.move_type == "CALL":
                return -0.45
            if candidate.move_type == "RAISE":
                return -0.55
            if candidate.move_type == "ALL_IN":
                return -0.60
            return 0.0
        if candidate.move_type == "RAISE":
            return max(0.0, equity - 0.72) * 0.95 - max(0.0, 0.68 - equity) * 0.25
        if candidate.move_type == "CALL":
            return max(-0.20, 0.04 - abs(equity - 0.66) * 1.10)
        if candidate.move_type == "FOLD":
            return max(0.0, 0.60 - equity) * 1.35 + features.recent_raise_pressure * 0.12
        if candidate.move_type == "ALL_IN":
            return max(0.0, equity - 0.66) * 1.10 + (0.15 if short_stack else 0.0)
        return 0.0

    if candidate.move_type == "ALL_IN":
        return max(0.0, equity - 0.50) * 1.35 + (1 - features.spr_score) * 0.20
    if candidate.move_type == "CALL":
        return max(0.0, equity - 0.52) * 0.30
    if candidate.move_type == "FOLD":
        return max(0.0, 0.48 - equity) * 1.10
    if candidate.move_type == "RAISE":
        return -0.35
    return 0.0
