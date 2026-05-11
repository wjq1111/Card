from __future__ import annotations

from dataclasses import dataclass
import random

from src.server.bots.controller import play_bot_turn
from src.server.bots.models import BotProfile, ScoreWeights
from src.server.room import BIG_BLIND, PokerRoom


@dataclass(frozen=True)
class BotMatchStats:
    player_id: str
    profile_name: str
    weights_name: str
    hands_played: int
    decision_count: int
    chip_delta: int
    wins: int
    folds: int
    checks: int
    calls: int
    raises: int
    all_ins: int

    @property
    def bb_per_100(self) -> float:
        if self.hands_played <= 0:
            return 0.0
        return self.chip_delta / BIG_BLIND / self.hands_played * 100.0

    def action_rates(self) -> dict[str, float]:
        total = max(1, self.decision_count)
        return {
            "fold_rate": self.folds / total,
            "check_rate": self.checks / total,
            "call_rate": self.calls / total,
            "raise_rate": self.raises / total,
            "all_in_rate": self.all_ins / total,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "player_id": self.player_id,
            "profile_name": self.profile_name,
            "weights_name": self.weights_name,
            "hands_played": self.hands_played,
            "decision_count": self.decision_count,
            "chip_delta": self.chip_delta,
            "bb_per_100": round(self.bb_per_100, 4),
            "wins": self.wins,
            "folds": self.folds,
            "checks": self.checks,
            "calls": self.calls,
            "raises": self.raises,
            "all_ins": self.all_ins,
            "rates": {key: round(value, 4) for key, value in self.action_rates().items()},
        }


@dataclass(frozen=True)
class BotMatchReport:
    seeds: tuple[int, ...]
    stats: dict[str, BotMatchStats]

    def as_dict(self) -> dict[str, object]:
        return {
            "seeds": list(self.seeds),
            "stats": {player_id: stats.as_dict() for player_id, stats in self.stats.items()},
        }


@dataclass(frozen=True)
class ProfileFitness:
    bb_per_100: float
    style_penalty: float
    fitness: float
    report: BotMatchReport

    def as_dict(self) -> dict[str, object]:
        return {
            "bb_per_100": round(self.bb_per_100, 4),
            "style_penalty": round(self.style_penalty, 4),
            "fitness": round(self.fitness, 4),
            "report": self.report.as_dict(),
        }


def simulate_heads_up_match(
    profile_a: BotProfile,
    profile_b: BotProfile,
    *,
    weights_a: ScoreWeights | None = None,
    weights_b: ScoreWeights | None = None,
    player_a_id: str = "bot_a",
    player_b_id: str = "bot_b",
    seeds: list[int] | tuple[int, ...],
) -> BotMatchReport:
    weights_a = weights_a or ScoreWeights()
    weights_b = weights_b or ScoreWeights()
    action_counts = {
        player_a_id: {"FOLD": 0, "CHECK": 0, "CALL": 0, "RAISE": 0, "ALL_IN": 0},
        player_b_id: {"FOLD": 0, "CHECK": 0, "CALL": 0, "RAISE": 0, "ALL_IN": 0},
    }
    decision_counts = {player_a_id: 0, player_b_id: 0}
    chip_deltas = {player_a_id: 0, player_b_id: 0}
    wins = {player_a_id: 0, player_b_id: 0}

    for hand_index, seed in enumerate(seeds):
        room = PokerRoom(f"sim-{seed}", rng=random.Random(seed), hand_complete_pause=0.0)
        first_id, second_id = seat_assignment_for_hand(player_a_id, player_b_id, hand_index)
        first_profile, second_profile = (
            (profile_a, profile_b) if first_id == player_a_id else (profile_b, profile_a)
        )
        first_weights, second_weights = (
            (weights_a, weights_b) if first_id == player_a_id else (weights_b, weights_a)
        )

        room.join(first_id, first_id)
        room.join(second_id, second_id)
        room.sit(first_id, 0)
        room.sit(second_id, 1)
        room.set_ready(first_id, True)
        room.set_ready(second_id, True)
        room.start_hand()

        rng_map = {
            player_a_id: random.Random(seed * 101 + 17),
            player_b_id: random.Random(seed * 101 + 29),
        }
        profile_map = {first_id: first_profile, second_id: second_profile}
        weights_map = {first_id: first_weights, second_id: second_weights}

        while room.last_hand_summary is None:
            active_player_id = room.seats[room.active_seat].player_id
            decision = play_bot_turn(
                room,
                active_player_id,
                profile=profile_map[active_player_id],
                weights=weights_map[active_player_id],
                rng=rng_map[active_player_id],
            )
            decision_counts[active_player_id] += 1
            action_counts[active_player_id][decision.move_type] += 1

        summary = room.last_hand_summary
        seat_to_player = {seat.seat_index: seat.player_id for seat in room.seats if seat.player_id}
        for seat_index, delta in summary.chip_deltas.items():
            chip_deltas[seat_to_player[seat_index]] += delta
        for seat_index in summary.winner_seats:
            wins[seat_to_player[seat_index]] += 1

    stats = {
        player_a_id: build_stats(player_a_id, profile_a, weights_a, len(seeds), decision_counts[player_a_id], chip_deltas[player_a_id], wins[player_a_id], action_counts[player_a_id]),
        player_b_id: build_stats(player_b_id, profile_b, weights_b, len(seeds), decision_counts[player_b_id], chip_deltas[player_b_id], wins[player_b_id], action_counts[player_b_id]),
    }
    return BotMatchReport(seeds=tuple(seeds), stats=stats)


def build_stats(
    player_id: str,
    profile: BotProfile,
    weights: ScoreWeights,
    hands_played: int,
    decision_count: int,
    chip_delta: int,
    wins: int,
    actions: dict[str, int],
) -> BotMatchStats:
    return BotMatchStats(
        player_id=player_id,
        profile_name=profile.name,
        weights_name=weights.name,
        hands_played=hands_played,
        decision_count=decision_count,
        chip_delta=chip_delta,
        wins=wins,
        folds=actions["FOLD"],
        checks=actions["CHECK"],
        calls=actions["CALL"],
        raises=actions["RAISE"],
        all_ins=actions["ALL_IN"],
    )


def seat_assignment_for_hand(player_a_id: str, player_b_id: str, hand_index: int) -> tuple[str, str]:
    if hand_index % 2 == 0:
        return player_a_id, player_b_id
    return player_b_id, player_a_id


def build_seed_series(seed: int, hands: int) -> list[int]:
    return [seed + offset for offset in range(hands)]


def evaluate_profile_quality(
    candidate: BotProfile,
    baseline: BotProfile,
    *,
    candidate_weights: ScoreWeights | None = None,
    baseline_weights: ScoreWeights | None = None,
    seeds: list[int] | tuple[int, ...],
    candidate_id: str = "candidate",
    baseline_id: str = "baseline",
) -> ProfileFitness:
    report = simulate_heads_up_match(
        candidate,
        baseline,
        weights_a=candidate_weights,
        weights_b=baseline_weights,
        player_a_id=candidate_id,
        player_b_id=baseline_id,
        seeds=seeds,
    )
    candidate_stats = report.stats[candidate_id]
    penalty = style_penalty(candidate_stats)
    bb_per_100 = candidate_stats.bb_per_100
    return ProfileFitness(bb_per_100=bb_per_100, style_penalty=penalty, fitness=bb_per_100 - penalty, report=report)


def style_penalty(stats: BotMatchStats) -> float:
    rates = stats.action_rates()
    penalty = 0.0
    penalty += max(0.0, rates["all_in_rate"] - 0.08) * 150.0
    penalty += max(0.0, 0.08 - rates["raise_rate"]) * 40.0
    penalty += max(0.0, rates["fold_rate"] - 0.80) * 50.0
    penalty += max(0.0, 0.05 - rates["call_rate"]) * 30.0
    return penalty


def mutate_profile(profile: BotProfile, rng: random.Random, *, step: float = 0.10, name: str | None = None) -> BotProfile:
    return BotProfile(
        name=name or profile.name,
        looseness=clip01(profile.looseness + rng.uniform(-step, step)),
        aggression=clip01(profile.aggression + rng.uniform(-step, step)),
        bluff_rate=clip01(profile.bluff_rate + rng.uniform(-step, step)),
        risk_tolerance=clip01(profile.risk_tolerance + rng.uniform(-step, step)),
        randomness=profile.randomness,
    )


def mutate_weights(weights: ScoreWeights, rng: random.Random, *, step: float = 0.08, name: str | None = None) -> ScoreWeights:
    updated: dict[str, float | str] = {"name": name or weights.name}
    for field_name, value in weights.as_dict().items():
        if field_name == "name":
            continue
        assert isinstance(value, float)
        next_value = value + rng.uniform(-step, step)
        if field_name.endswith("_threshold"):
            next_value = clip01(next_value)
        updated[field_name] = next_value
    return weights.updated(**updated)


def tune_profile(
    initial: BotProfile,
    baseline: BotProfile,
    *,
    seeds: list[int] | tuple[int, ...],
    iterations: int = 12,
    candidates_per_iteration: int = 6,
    mutation_step: float = 0.10,
    rng: random.Random | None = None,
) -> tuple[BotProfile, ProfileFitness, list[dict[str, object]]]:
    rng = rng or random.Random()
    best_profile = initial
    best_fitness = evaluate_profile_quality(best_profile, baseline, seeds=seeds)
    history = [
        {
            "iteration": 0,
            "profile": best_profile.as_dict(),
            "fitness": round(best_fitness.fitness, 4),
            "bb_per_100": round(best_fitness.bb_per_100, 4),
            "style_penalty": round(best_fitness.style_penalty, 4),
        }
    ]

    for iteration in range(1, iterations + 1):
        local_best_profile = best_profile
        local_best_fitness = best_fitness
        for candidate_index in range(candidates_per_iteration):
            candidate = mutate_profile(best_profile, rng, step=mutation_step, name=f"{initial.name}_iter{iteration}_{candidate_index}")
            fitness = evaluate_profile_quality(candidate, baseline, seeds=seeds)
            if fitness.fitness > local_best_fitness.fitness:
                local_best_profile = candidate
                local_best_fitness = fitness

        best_profile = local_best_profile
        best_fitness = local_best_fitness
        history.append(
            {
                "iteration": iteration,
                "profile": best_profile.as_dict(),
                "fitness": round(best_fitness.fitness, 4),
                "bb_per_100": round(best_fitness.bb_per_100, 4),
                "style_penalty": round(best_fitness.style_penalty, 4),
            }
        )

    return best_profile, best_fitness, history


def tune_weights(
    initial: ScoreWeights,
    baseline: ScoreWeights,
    *,
    candidate_profile: BotProfile,
    baseline_profile: BotProfile,
    seeds: list[int] | tuple[int, ...],
    iterations: int = 12,
    candidates_per_iteration: int = 6,
    mutation_step: float = 0.08,
    rng: random.Random | None = None,
) -> tuple[ScoreWeights, ProfileFitness, list[dict[str, object]]]:
    rng = rng or random.Random()
    best_weights = initial
    best_fitness = evaluate_profile_quality(
        candidate_profile,
        baseline_profile,
        candidate_weights=best_weights,
        baseline_weights=baseline,
        seeds=seeds,
    )
    history = [
        {
            "iteration": 0,
            "weights": best_weights.as_dict(),
            "fitness": round(best_fitness.fitness, 4),
            "bb_per_100": round(best_fitness.bb_per_100, 4),
            "style_penalty": round(best_fitness.style_penalty, 4),
        }
    ]

    for iteration in range(1, iterations + 1):
        local_best_weights = best_weights
        local_best_fitness = best_fitness
        for candidate_index in range(candidates_per_iteration):
            candidate = mutate_weights(best_weights, rng, step=mutation_step, name=f"{initial.name}_iter{iteration}_{candidate_index}")
            fitness = evaluate_profile_quality(
                candidate_profile,
                baseline_profile,
                candidate_weights=candidate,
                baseline_weights=baseline,
                seeds=seeds,
            )
            if fitness.fitness > local_best_fitness.fitness:
                local_best_weights = candidate
                local_best_fitness = fitness

        best_weights = local_best_weights
        best_fitness = local_best_fitness
        history.append(
            {
                "iteration": iteration,
                "weights": best_weights.as_dict(),
                "fitness": round(best_fitness.fitness, 4),
                "bb_per_100": round(best_fitness.bb_per_100, 4),
                "style_penalty": round(best_fitness.style_penalty, 4),
            }
        )

    return best_weights, best_fitness, history


def clip01(value: float) -> float:
    return max(0.0, min(1.0, value))
