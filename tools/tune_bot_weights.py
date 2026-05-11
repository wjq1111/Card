from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


from src.server.bots.models import BotProfile, ScoreWeights
from src.server.bots.simulation import build_seed_series, tune_weights


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune bot score weights against a baseline with deterministic seeds.")
    parser.add_argument("--hands", type=int, default=200, help="Hands per evaluation.")
    parser.add_argument("--seed", type=int, default=17, help="Base seed for deterministic hands.")
    parser.add_argument("--iterations", type=int, default=10, help="Number of tuning iterations.")
    parser.add_argument("--candidates", type=int, default=6, help="Mutated weight sets per iteration.")
    parser.add_argument("--mutation-step", type=float, default=0.08, help="Max mutation size per weight.")
    parser.add_argument("--tuner-seed", type=int, default=321, help="Seed for weight mutation.")
    parser.add_argument("--candidate-name", default="candidate_weights")
    parser.add_argument("--baseline-name", default="baseline_weights")
    parser.add_argument("--profile-name", default="candidate_profile")
    parser.add_argument("--baseline-profile-name", default="baseline_profile")
    parser.add_argument("--looseness", type=float, default=0.50)
    parser.add_argument("--aggression", type=float, default=0.45)
    parser.add_argument("--bluff-rate", type=float, default=0.08)
    parser.add_argument("--risk-tolerance", type=float, default=0.45)
    parser.add_argument("--baseline-looseness", type=float, default=0.50)
    parser.add_argument("--baseline-aggression", type=float, default=0.45)
    parser.add_argument("--baseline-bluff-rate", type=float, default=0.08)
    parser.add_argument("--baseline-risk-tolerance", type=float, default=0.45)
    parser.add_argument("--json", action="store_true", help="Print JSON summary.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidate_profile = BotProfile(
        name=args.profile_name,
        looseness=args.looseness,
        aggression=args.aggression,
        bluff_rate=args.bluff_rate,
        risk_tolerance=args.risk_tolerance,
        randomness=0.0,
    )
    baseline_profile = BotProfile(
        name=args.baseline_profile_name,
        looseness=args.baseline_looseness,
        aggression=args.baseline_aggression,
        bluff_rate=args.baseline_bluff_rate,
        risk_tolerance=args.baseline_risk_tolerance,
        randomness=0.0,
    )
    seeds = build_seed_series(args.seed, args.hands)
    best_weights, best_fitness, history = tune_weights(
        ScoreWeights(name=args.candidate_name),
        ScoreWeights(name=args.baseline_name),
        candidate_profile=candidate_profile,
        baseline_profile=baseline_profile,
        seeds=seeds,
        iterations=args.iterations,
        candidates_per_iteration=args.candidates,
        mutation_step=args.mutation_step,
        rng=random.Random(args.tuner_seed),
    )

    print(f"Tuned weights over {args.hands} hands and {args.iterations} iterations")
    print(f"Best fitness={best_fitness.fitness:.4f} bb_per_100={best_fitness.bb_per_100:.4f} penalty={best_fitness.style_penalty:.4f}")
    print("Best weights:")
    print(json.dumps(best_weights.as_dict(), ensure_ascii=False, indent=2))

    if args.json:
        payload = {
            "best_weights": best_weights.as_dict(),
            "fitness": best_fitness.as_dict(),
            "history": history,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
