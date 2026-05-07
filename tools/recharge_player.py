from __future__ import annotations

import argparse

from server.chip_store import PlayerChipStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recharge a player's chips in the local server file store.")
    parser.add_argument("--name", required=True, help="Player name used at login.")
    parser.add_argument("--amount", required=True, type=int, help="Positive or negative chip delta.")
    parser.add_argument(
        "--store",
        default="runtime_logs/player_chips.json",
        help="Chip store JSON path. Defaults to runtime_logs/player_chips.json.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    store = PlayerChipStore(args.store)
    before = store.get_or_create(args.name)
    after = store.add_chips(args.name, args.amount)
    print(f"{args.name}: {before} -> {after} ({args.amount:+d})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
