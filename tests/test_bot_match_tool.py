import unittest

from src.server.bots.simulation import BotMatchStats
from tools.run_bot_match import report_summary


class BotMatchToolReportTest(unittest.TestCase):
    def test_report_summary_flags_unnatural_rates(self) -> None:
        stats = BotMatchStats(
            player_id="bot_a",
            profile_name="candidate",
            weights_name="default",
            hands_played=100,
            decision_count=100,
            chip_delta=0,
            wins=50,
            folds=60,
            checks=10,
            calls=5,
            raises=20,
            all_ins=5,
        )

        summary = report_summary(stats)

        self.assertIn("style_penalty", summary)
        self.assertIn("fitness", summary)
        self.assertTrue(any("fold_rate is high" in note for note in summary["notes"]))
        self.assertTrue(any("call_rate is low" in note for note in summary["notes"]))


if __name__ == "__main__":
    unittest.main()
