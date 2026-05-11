import unittest
from tempfile import TemporaryDirectory

from src.server.minimax_bots.document_io import (
    INPUT_END,
    INPUT_START,
    OUTPUT_END,
    OUTPUT_START,
    MiniMaxTurnPrompt,
    load_bot_document,
    render_turn_prompt,
    write_bot_output,
)


class MiniMaxBotDocumentTest(unittest.TestCase):
    def test_render_turn_prompt_uses_structured_sections(self) -> None:
        prompt = MiniMaxTurnPrompt(
            room_id="room-1",
            hand_id="room-1-000001-abcd1234",
            bot_id="minimax:1",
            phase="FLOP",
            hero_seat=3,
            hero_cards="Ah Kd",
            board_cards="Qs Jh 2c",
            pot=120,
            current_bet=40,
            min_raise=40,
            to_call=40,
            chips=1880,
            committed=0,
            legal_actions=("FOLD", "CALL", "RAISE", "ALL_IN"),
            action_history=(
                "PREFLOP | S1 Alice | SMALL_BLIND | amount=10",
                "PREFLOP | S2 Bob | BIG_BLIND | amount=20",
                "PREFLOP | S3 MiniMax Bot | CALL | amount=20",
            ),
        )

        text = render_turn_prompt(prompt)

        self.assertIn("[当前牌面信息]", text)
        self.assertIn("phase: FLOP", text)
        self.assertIn("hero_cards: Ah Kd", text)
        self.assertIn("[之前所有人的操作信息]", text)
        self.assertIn("1. PREFLOP | S1 Alice | SMALL_BLIND | amount=10", text)
        self.assertIn("legal_actions: FOLD, CALL, RAISE, ALL_IN", text)

    def test_document_output_section_is_replaced_in_place(self) -> None:
        source = "\n".join(
            [
                "# MiniMax Bot Turn",
                "",
                INPUT_START,
                "test input",
                INPUT_END,
                "",
                OUTPUT_START,
                "pending",
                OUTPUT_END,
                "",
            ]
        )
        new_output = "\n".join(
            [
                "move_type: CALL",
                "amount: 0",
                "reason: 底池赔率合适。",
            ]
        )

        with TemporaryDirectory() as temp_dir:
            path = temp_dir + "/turn.md"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(source)

            write_bot_output(path, new_output)
            document = load_bot_document(path)

            self.assertEqual(document.input_text, "test input")
            self.assertEqual(document.output_text, new_output)


if __name__ == "__main__":
    unittest.main()
