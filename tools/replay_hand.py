from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from src.shared.game_logging import GameLogStore
from src.shared.hand_replay import load_hand_replay, render_hand_replay


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a structured replay for one logged poker hand.")
    parser.add_argument("--logs-root", default="runtime_logs", help="Root directory that contains runtime logs.")
    parser.add_argument("--scope", default="server", help="Log scope. Defaults to the server runtime logs.")
    parser.add_argument("--owner", default="rooms", help="Log owner bucket used by GameLogStore.")
    parser.add_argument("--room-id", help="Room id that owns the hand log.")
    parser.add_argument("--hand-id", help="Exact hand id to replay.")
    parser.add_argument("--hand-number", type=int, help="Optional hand number to disambiguate a hand id.")
    parser.add_argument("--file", help="Replay a specific hand jsonl file directly.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.file and (not args.room_id or not args.hand_id):
        raise SystemExit("--file or both --room-id and --hand-id are required")

    store = GameLogStore(Path(args.logs_root), args.scope, args.owner)
    replay = load_hand_replay(
        store,
        room_id=args.room_id or "",
        hand_id=args.hand_id,
        hand_number=args.hand_number,
        path=args.file,
    )
    print(render_hand_replay(replay))


if __name__ == "__main__":
    main()
