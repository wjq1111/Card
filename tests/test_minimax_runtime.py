import unittest

from src.server.minimax_bots.runtime import parse_decision


class MiniMaxRuntimeParseTest(unittest.TestCase):
    def test_parse_decision_accepts_strict_template(self) -> None:
        decision = parse_decision(
            "move_type: CALL\namount: 0\nreason: 底池赔率合适。",
            ("FOLD", "CALL", "RAISE", "ALL_IN"),
        )
        self.assertEqual(decision.move_type, "CALL")
        self.assertEqual(decision.amount, 0)
        self.assertEqual(decision.source, "model")

    def test_parse_decision_accepts_json_action_payload(self) -> None:
        decision = parse_decision(
            '{"action":"RAISE","amount":80,"reasoning":"牌力领先"}',
            ("FOLD", "CALL", "RAISE", "ALL_IN"),
        )
        self.assertEqual(decision.move_type, "RAISE")
        self.assertEqual(decision.amount, 80)
        self.assertEqual(decision.source, "model")

    def test_parse_decision_accepts_bare_action_keyword(self) -> None:
        decision = parse_decision(
            "CALL",
            ("FOLD", "CALL", "RAISE", "ALL_IN"),
        )
        self.assertEqual(decision.move_type, "CALL")
        self.assertEqual(decision.amount, 0)
        self.assertEqual(decision.source, "model")


if __name__ == "__main__":
    unittest.main()
