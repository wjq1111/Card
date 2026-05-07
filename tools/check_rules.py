from __future__ import annotations

import sys
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


RULE_CASES = [
    ("RC-01", "少于两名准备玩家时不能开局"),
    ("RC-02", "单挑时庄家下小盲并先行动"),
    ("RC-03", "面对下注时不能过牌"),
    ("RC-04", "加注不能低于最小加注额"),
    ("RC-05", "短码全下不会错误改变最小加注额"),
    ("RC-06", "其余玩家弃牌后应直接赢池"),
    ("RC-07", "所有可行动玩家完成本轮动作后才进入下一街"),
    ("RC-08", "七张牌中自动选出最优五张"),
    ("RC-09", "A-2-3-4-5 识别为轮顺"),
    ("RC-10", "同对子时由踢脚决定胜负"),
    ("RC-11", "边池只允许有资格玩家争夺"),
    ("RC-12", "弃牌玩家保留贡献但不能赢池"),
    ("RC-13", "平分底池时筹码变化守恒"),
]

TEST_MODULES = [
    "tests.test_hand_evaluator",
    "tests.test_room",
    "tests.test_settlement",
    "tests.test_rule_cases",
    "tests.test_client_ui",
]


def main() -> int:
    print("Texas Holdem rule check")
    print("=" * 32)
    for case_id, description in RULE_CASES:
        print(f"[{case_id}] {description}")
    print()

    suite = unittest.TestLoader().loadTestsFromNames(TEST_MODULES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
