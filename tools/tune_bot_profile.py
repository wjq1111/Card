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


from src.server.bots.models import BotProfile
from src.server.bots.simulation import build_seed_series, tune_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune a bot profile against a baseline with deterministic seeds.")
    parser.add_argument("--hands", type=int, default=200, help="Hands per evaluation.")
    parser.add_argument("--seed", type=int, default=11, help="Base seed for deterministic hands.")
    parser.add_argument("--iterations", type=int, default=10, help="Number of tuning iterations.")
    parser.add_argument("--candidates", type=int, default=6, help="Mutated candidates per iteration.")
    parser.add_argument("--mutation-step", type=float, default=0.10, help="Max mutation size per parameter.")
    parser.add_argument("--tuner-seed", type=int, default=123, help="Seed for parameter mutation.")
    parser.add_argument("--name", default="candidate", help="Name label for the tuned profile.")
    parser.add_argument("--looseness", type=float, default=0.50)
    parser.add_argument("--aggression", type=float, default=0.45)
    parser.add_argument("--bluff-rate", type=float, default=0.08)
    parser.add_argument("--risk-tolerance", type=float, default=0.45)
    parser.add_argument("--baseline-name", default="baseline")
    parser.add_argument("--baseline-looseness", type=float, default=0.50)
    parser.add_argument("--baseline-aggression", type=float, default=0.45)
    parser.add_argument("--baseline-bluff-rate", type=float, default=0.08)
    parser.add_argument("--baseline-risk-tolerance", type=float, default=0.45)
    parser.add_argument("--json", action="store_true", help="Print JSON summary.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    initial = BotProfile(
        name=args.name,
        looseness=args.looseness,
        aggression=args.aggression,
        bluff_rate=args.bluff_rate,
        risk_tolerance=args.risk_tolerance,
        randomness=0.0,
    )
    baseline = BotProfile(
        name=args.baseline_name,
        looseness=args.baseline_looseness,
        aggression=args.baseline_aggression,
        bluff_rate=args.baseline_bluff_rate,
        risk_tolerance=args.baseline_risk_tolerance,
        randomness=0.0,
    )
    seeds = build_seed_series(args.seed, args.hands)
    best_profile, best_fitness, history = tune_profile(
        initial,
        baseline,
        seeds=seeds,
        iterations=args.iterations,
        candidates_per_iteration=args.candidates,
        mutation_step=args.mutation_step,
        rng=random.Random(args.tuner_seed),
    )

    print(f"Tuned profile over {args.hands} hands and {args.iterations} iterations")
    print(f"Best fitness={best_fitness.fitness:.4f} bb_per_100={best_fitness.bb_per_100:.4f} penalty={best_fitness.style_penalty:.4f}")
    print("Best profile:")
    print(json.dumps(best_profile.as_dict(), ensure_ascii=False, indent=2))

    if args.json:
        payload = {
            "best_profile": best_profile.as_dict(),
            "fitness": best_fitness.as_dict(),
            "history": history,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
