import random
import unittest

from src.server.bots.models import BotProfile, ScoreWeights
from src.server.bots.simulation import (
    BotMatchStats,
    build_seed_series,
    evaluate_profile_quality,
    simulate_heads_up_match,
    style_penalty,
    tune_profile,
    tune_weights,
)
from src.shared.cards import shuffled_deck


class BotSimulationTest(unittest.TestCase):
    def test_shuffled_deck_is_deterministic_with_rng(self) -> None:
        deck_a = shuffled_deck(random.Random(5))
        deck_b = shuffled_deck(random.Random(5))

        self.assertEqual(deck_a, deck_b)

    def test_match_report_is_repeatable_for_same_seed_series(self) -> None:
        profile_a = BotProfile(name="a", randomness=0.0)
        profile_b = BotProfile(name="b", aggression=0.55, randomness=0.0)
        seeds = build_seed_series(13, 20)

        report_one = simulate_heads_up_match(profile_a, profile_b, seeds=seeds)
        report_two = simulate_heads_up_match(profile_a, profile_b, seeds=seeds)

        self.assertEqual(report_one.as_dict(), report_two.as_dict())

    def test_style_penalty_punishes_extreme_all_in_frequency(self) -> None:
        wild = BotMatchStats(
            player_id="wild",
            profile_name="wild",
            weights_name="wild",
            hands_played=50,
            decision_count=100,
            chip_delta=0,
            wins=25,
            folds=10,
            checks=10,
            calls=10,
            raises=10,
            all_ins=60,
        )

        steady = BotMatchStats(
            player_id="steady",
            profile_name="steady",
            weights_name="steady",
            hands_played=50,
            decision_count=100,
            chip_delta=0,
            wins=25,
            folds=20,
            checks=20,
            calls=25,
            raises=30,
            all_ins=5,
        )

        self.assertGreater(style_penalty(wild), style_penalty(steady))

    def test_tune_profile_returns_history_and_deterministic_best_profile(self) -> None:
        initial = BotProfile(name="candidate", randomness=0.0)
        baseline = BotProfile(name="baseline", aggression=0.55, randomness=0.0)
        seeds = build_seed_series(21, 30)

        best_profile_one, best_fitness_one, history_one = tune_profile(
            initial,
            baseline,
            seeds=seeds,
            iterations=3,
            candidates_per_iteration=3,
            mutation_step=0.08,
            rng=random.Random(9),
        )
        best_profile_two, best_fitness_two, history_two = tune_profile(
            initial,
            baseline,
            seeds=seeds,
            iterations=3,
            candidates_per_iteration=3,
            mutation_step=0.08,
            rng=random.Random(9),
        )

        self.assertEqual(best_profile_one.as_dict(), best_profile_two.as_dict())
        self.assertEqual(best_fitness_one.as_dict(), best_fitness_two.as_dict())
        self.assertEqual(history_one, history_two)
        self.assertEqual(len(history_one), 4)

    def test_quality_report_wraps_match_report(self) -> None:
        candidate = BotProfile(name="candidate", randomness=0.0)
        baseline = BotProfile(name="baseline", randomness=0.0)
        fitness = evaluate_profile_quality(candidate, baseline, seeds=build_seed_series(31, 10))

        self.assertIn("candidate", fitness.report.stats)
        self.assertIn("baseline", fitness.report.stats)

    def test_tune_weights_returns_deterministic_best_weights(self) -> None:
        candidate_profile = BotProfile(name="candidate", randomness=0.0)
        baseline_profile = BotProfile(name="baseline", randomness=0.0)
        initial = ScoreWeights(name="initial")
        baseline = ScoreWeights(name="baseline")
        seeds = build_seed_series(41, 30)

        best_weights_one, best_fitness_one, history_one = tune_weights(
            initial,
            baseline,
            candidate_profile=candidate_profile,
            baseline_profile=baseline_profile,
            seeds=seeds,
            iterations=2,
            candidates_per_iteration=3,
            mutation_step=0.05,
            rng=random.Random(6),
        )
        best_weights_two, best_fitness_two, history_two = tune_weights(
            initial,
            baseline,
            candidate_profile=candidate_profile,
            baseline_profile=baseline_profile,
            seeds=seeds,
            iterations=2,
            candidates_per_iteration=3,
            mutation_step=0.05,
            rng=random.Random(6),
        )

        self.assertEqual(best_weights_one.as_dict(), best_weights_two.as_dict())
        self.assertEqual(best_fitness_one.as_dict(), best_fitness_two.as_dict())
        self.assertEqual(history_one, history_two)


if __name__ == "__main__":
    unittest.main()
