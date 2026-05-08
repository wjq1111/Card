from __future__ import annotations

import sys
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


RULE_CASES = [
    ("RC-01", "Cannot start a hand with fewer than two ready players."),
    ("RC-02", "Heads-up dealer posts the small blind and acts first preflop."),
    ("RC-03", "A player cannot check while facing a bet."),
    ("RC-04", "Raise amount cannot be below the minimum raise."),
    ("RC-05", "Short all-in raises the call line without reducing min-raise."),
    ("RC-06", "Last live player wins the pot without showdown."),
    ("RC-07", "A street advances only after all actionable players finish."),
    ("RC-08", "Best five cards are selected automatically from seven."),
    ("RC-09", "A-2-3-4-5 is recognized as a wheel straight."),
    ("RC-10", "Kickers break ties for matching made hands."),
    ("RC-11", "Side pots are contested only by eligible players."),
    ("RC-12", "Folded players keep contributions but cannot win."),
    ("RC-13", "Split pots preserve total chip balance."),
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
