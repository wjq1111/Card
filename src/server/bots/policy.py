from __future__ import annotations

import random

from src.server.bots.features import clamp, extract_features
from src.server.bots.models import ActionCandidate, ActionScore, BotDecision, BotFeatures, BotObservation, BotProfile, ScoreWeights


def decide_action(
    observation: BotObservation,
    profile: BotProfile | None = None,
    weights: ScoreWeights | None = None,
    rng: random.Random | None = None,
) -> BotDecision:
    profile = profile or BotProfile()
    weights = weights or ScoreWeights()
    rng = rng or random.Random()
    features = extract_features(observation, profile)
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
        for ratio in (0.50, 0.75):
            target = raise_target_for_ratio(observation, ratio)
            if observation.minimum_raise_to <= target < observation.maximum_raise_to:
                candidate = ActionCandidate("RAISE", target)
                if candidate not in candidates:
                    candidates.append(candidate)

    if "ALL_IN" in legal:
        candidates.append(ActionCandidate("ALL_IN"))

    return tuple(candidates)


def raise_target_for_ratio(observation: BotObservation, ratio: float) -> int:
    target = observation.committed + observation.to_call + round(observation.pot * ratio)
    target = max(target, observation.minimum_raise_to)
    return min(target, observation.maximum_raise_to)


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

    if profile.randomness > 0:
        score += rng.uniform(-profile.randomness, profile.randomness)
    return ActionScore(candidate.move_type, candidate.amount, score)


def score_check(features: BotFeatures, profile: BotProfile, weights: ScoreWeights) -> float:
    return (
        weights.check_made_strength * features.made_strength
        + weights.check_draw_strength * features.draw_strength
        + weights.check_position_score * features.position_score
        + weights.check_board_wetness * features.board_wetness
        + weights.check_passive_bias * (1 - profile.aggression)
    )


def score_call(features: BotFeatures, profile: BotProfile, weights: ScoreWeights) -> float:
    return (
        weights.call_made_strength * features.made_strength
        + weights.call_draw_strength * features.draw_strength
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
        + weights.all_in_low_spr * (1 - features.spr_score)
        + weights.all_in_risk_tolerance * profile.risk_tolerance
        + weights.all_in_aggression * profile.aggression
        + weights.all_in_bad_pot_odds * (1 - features.pot_odds_fit)
    )
    if features.made_strength < weights.all_in_made_threshold and features.draw_strength < weights.all_in_draw_threshold:
        score += weights.all_in_weak_penalty
    return score
