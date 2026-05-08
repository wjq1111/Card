from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


from src.server.bots.models import BotProfile, ScoreWeights
from src.server.bots.simulation import BotMatchStats, build_seed_series, simulate_heads_up_match, style_penalty


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a deterministic bot-vs-bot match.")
    parser.add_argument("--hands", type=int, default=100, help="Number of hands to simulate.")
    parser.add_argument("--seed", type=int, default=7, help="Base seed for deterministic hand generation.")
    parser.add_argument("--profile-a", default="balanced", help="Name label for bot A.")
    parser.add_argument("--profile-b", default="baseline", help="Name label for bot B.")
    parser.add_argument("--weights-a", default="default", help="Name label for weight set A.")
    parser.add_argument("--weights-b", default="default", help="Name label for weight set B.")
    parser.add_argument("--a-looseness", type=float, default=0.50)
    parser.add_argument("--a-aggression", type=float, default=0.45)
    parser.add_argument("--a-bluff-rate", type=float, default=0.08)
    parser.add_argument("--a-risk-tolerance", type=float, default=0.45)
    parser.add_argument("--b-looseness", type=float, default=0.50)
    parser.add_argument("--b-aggression", type=float, default=0.45)
    parser.add_argument("--b-bluff-rate", type=float, default=0.08)
    parser.add_argument("--b-risk-tolerance", type=float, default=0.45)
    parser.add_argument("--call-opponent-aggression-a", type=float, default=0.15)
    parser.add_argument("--fold-recent-raise-pressure-a", type=float, default=0.20)
    parser.add_argument("--raise-opponent-fold-to-raise-a", type=float, default=0.20)
    parser.add_argument("--raise-opponent-vpip-a", type=float, default=-0.10)
    parser.add_argument("--call-opponent-aggression-b", type=float, default=0.15)
    parser.add_argument("--fold-recent-raise-pressure-b", type=float, default=0.20)
    parser.add_argument("--raise-opponent-fold-to-raise-b", type=float, default=0.20)
    parser.add_argument("--raise-opponent-vpip-b", type=float, default=-0.10)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser.parse_args()


def build_weights(args: argparse.Namespace, side: str) -> ScoreWeights:
    suffix = side.lower()
    return ScoreWeights(
        name=getattr(args, f"weights_{suffix}"),
        call_opponent_aggression=getattr(args, f"call_opponent_aggression_{suffix}"),
        fold_recent_raise_pressure=getattr(args, f"fold_recent_raise_pressure_{suffix}"),
        raise_opponent_fold_to_raise=getattr(args, f"raise_opponent_fold_to_raise_{suffix}"),
        raise_opponent_vpip=getattr(args, f"raise_opponent_vpip_{suffix}"),
    )


def report_summary(stats: BotMatchStats) -> dict[str, object]:
    penalty = style_penalty(stats)
    fitness = stats.bb_per_100 - penalty
    rates = stats.action_rates()
    notes: list[str] = []
    if rates["fold_rate"] > 0.55:
        notes.append("fold_rate is high: the bot may be over-tight and giving up too often.")
    if rates["call_rate"] < 0.10:
        notes.append("call_rate is low: the bot may not defend enough against pressure.")
    if rates["raise_rate"] < 0.12:
        notes.append("raise_rate is low: the bot may miss value bets and steal spots.")
    if rates["raise_rate"] > 0.30:
        notes.append("raise_rate is high: verify that bluffs are not over-firing into sticky opponents.")
    if rates["all_in_rate"] > 0.08:
        notes.append("all_in_rate is high: the bot may feel unnatural or too swingy.")
    if not notes:
        notes.append("action frequencies look broadly stable; inspect win rate and matchup context next.")
    return {
        "style_penalty": round(penalty, 4),
        "fitness": round(fitness, 4),
        "notes": notes,
    }


def main() -> int:
    args = parse_args()
    profile_a = BotProfile(
        name=args.profile_a,
        looseness=args.a_looseness,
        aggression=args.a_aggression,
        bluff_rate=args.a_bluff_rate,
        risk_tolerance=args.a_risk_tolerance,
        randomness=0.0,
    )
    profile_b = BotProfile(
        name=args.profile_b,
        looseness=args.b_looseness,
        aggression=args.b_aggression,
        bluff_rate=args.b_bluff_rate,
        risk_tolerance=args.b_risk_tolerance,
        randomness=0.0,
    )
    weights_a = build_weights(args, "a")
    weights_b = build_weights(args, "b")
    seeds = build_seed_series(args.seed, args.hands)
    report = simulate_heads_up_match(
        profile_a,
        profile_b,
        weights_a=weights_a,
        weights_b=weights_b,
        player_a_id="bot_a",
        player_b_id="bot_b",
        seeds=seeds,
    )

    print(f"Bot match over {args.hands} hands")
    print(f"Seeds: {seeds[0]}..{seeds[-1]}")
    print()
    for player_id, stats in report.stats.items():
        rates = stats.action_rates()
        summary = report_summary(stats)
        print(f"{player_id} ({stats.profile_name}, weights={stats.weights_name})")
        print(f"  chip_delta={stats.chip_delta} bb_per_100={stats.bb_per_100:.2f} wins={stats.wins}")
        print(f"  style_penalty={summary['style_penalty']:.2f} fitness={summary['fitness']:.2f}")
        print(
            "  actions="
            f"fold:{stats.folds} check:{stats.checks} call:{stats.calls} raise:{stats.raises} all_in:{stats.all_ins}"
        )
        print(
            "  rates="
            f"fold:{rates['fold_rate']:.3f} check:{rates['check_rate']:.3f} call:{rates['call_rate']:.3f} "
            f"raise:{rates['raise_rate']:.3f} all_in:{rates['all_in_rate']:.3f}"
        )
        print("  notes=")
        for note in summary["notes"]:
            print(f"    - {note}")
        print()

    if args.json:
        payload = report.as_dict()
        payload["summaries"] = {
            player_id: report_summary(stats) for player_id, stats in report.stats.items()
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
