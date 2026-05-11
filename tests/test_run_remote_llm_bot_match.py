from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from src.shared.game_logging import GameLogStore


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "run_remote_llm_bot_match.py"
SPEC = importlib.util.spec_from_file_location("run_remote_llm_bot_match", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class RemoteLlmBotMatchToolTest(unittest.TestCase):
    def test_collect_hand_action_counts_groups_actions_per_player(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = GameLogStore(tmp_dir, "server", "rooms")
            hand_path = store.hand_log_jsonl_path("room-1", 1, "room-1-000001-test")
            hand_path.parent.mkdir(parents=True, exist_ok=True)
            rows = [
                {
                    "event_type": "ACTION",
                    "hand_id": "room-1-000001-test",
                    "data": {"player_id": "bot:score", "move_type": "CHECK"},
                },
                {
                    "event_type": "ACTION",
                    "hand_id": "room-1-000001-test",
                    "data": {"player_id": "minimax:llm", "move_type": "RAISE"},
                },
                {
                    "event_type": "ACTION",
                    "hand_id": "room-1-000001-test",
                    "data": {"player_id": "minimax:llm", "move_type": "CALL"},
                },
            ]
            hand_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            counts = MODULE.collect_hand_action_counts(store, "room-1", ["room-1-000001-test"])

        self.assertEqual(counts["bot:score"], Counter({"CHECK": 1}))
        self.assertEqual(counts["minimax:llm"], Counter({"RAISE": 1, "CALL": 1}))

    def test_collect_minimax_decisions_reads_room_log_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = GameLogStore(tmp_dir, "server", "rooms")
            room_log = store.room_log_path("room-1").with_suffix(".jsonl")
            room_log.parent.mkdir(parents=True, exist_ok=True)
            rows = [
                {
                    "event_type": "MINIMAX_BOT_DECISION",
                    "hand_id": "room-1-000001-test",
                    "data": {
                        "decision": {"move_type": "CALL", "amount": 0},
                        "source": "model",
                        "reason": "pot odds",
                        "transcript_path": "runtime_logs/minimax_bots/room-1/turn_001.md",
                        "raw_response": "move_type: CALL",
                    },
                },
                {
                    "event_type": "ACTION",
                    "hand_id": "room-1-000001-test",
                    "data": {},
                },
            ]
            room_log.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            decisions = MODULE.collect_minimax_decisions(store, "room-1", ["room-1-000001-test"])

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].move_type, "CALL")
        self.assertEqual(decisions[0].source, "model")
        self.assertEqual(decisions[0].reason, "pot odds")


if __name__ == "__main__":
    unittest.main()
