from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


INPUT_START = "<!-- MINIMAX_BOT_INPUT_START -->"
INPUT_END = "<!-- MINIMAX_BOT_INPUT_END -->"
OUTPUT_START = "<!-- MINIMAX_BOT_OUTPUT_START -->"
OUTPUT_END = "<!-- MINIMAX_BOT_OUTPUT_END -->"


SYSTEM_PROMPT = """你是一个非交互式德州扑克牌局机器人。
你只能依据给定的牌局信息做决策，不能虚构额外信息。
你必须严格遵守 legal_actions。
你必须只输出下面 3 行，不能输出标题、Markdown、JSON、代码块、额外解释。

固定输出格式:
move_type: <FOLD|CHECK|CALL|RAISE|ALL_IN>
amount: <整数；如果 move_type 不是 RAISE，必须填 0>
reason: <一句中文理由，不超过30个字>

硬性规则:
1. move_type 必须是 legal_actions 中的一个。
2. 如果 move_type 不是 RAISE，amount 必须是 0。
3. 如果 move_type 是 RAISE，amount 必须是一个大于 0 的整数。
4. 不要输出任何额外文字。

正确示例 1:
move_type: CHECK
amount: 0
reason: 当前无须跟注，先免费看下一张牌。

正确示例 2:
move_type: CALL
amount: 0
reason: 跟注成本低，底池赔率合适。

正确示例 3:
move_type: RAISE
amount: 80
reason: 牌力领先，主动加注获取价值。

错误示例 1:
{"action":"CALL","amount":0}

错误示例 2:
## 决策
CALL
"""


@dataclass(frozen=True)
class MiniMaxBotDocument:
    path: Path
    source_text: str
    input_text: str
    output_text: str


@dataclass(frozen=True)
class MiniMaxTurnPrompt:
    room_id: str
    hand_id: str
    bot_id: str
    phase: str
    hero_seat: int
    hero_cards: str
    board_cards: str
    pot: int
    current_bet: int
    min_raise: int
    to_call: int
    chips: int
    committed: int
    legal_actions: tuple[str, ...]
    action_history: tuple[str, ...]


def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    pattern = re.escape(start_marker) + r"\n?(.*?)\n?" + re.escape(end_marker)
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        raise ValueError("Document is missing section markers: {} ... {}".format(start_marker, end_marker))
    return match.group(1).strip()


def load_bot_document(path: str | Path) -> MiniMaxBotDocument:
    source_text = Path(path).read_text(encoding="utf-8")
    return MiniMaxBotDocument(
        path=Path(path),
        source_text=source_text,
        input_text=_extract_section(source_text, INPUT_START, INPUT_END),
        output_text=_extract_section(source_text, OUTPUT_START, OUTPUT_END),
    )


def replace_output_section(source_text: str, output_text: str) -> str:
    replacement = OUTPUT_START + "\n" + output_text.strip() + "\n" + OUTPUT_END
    pattern = re.escape(OUTPUT_START) + r"\n?.*?\n?" + re.escape(OUTPUT_END)
    return re.sub(pattern, replacement, source_text, count=1, flags=re.DOTALL)


def write_bot_output(path: str | Path, output_text: str) -> str:
    document = load_bot_document(path)
    updated = replace_output_section(document.source_text, output_text)
    Path(path).write_text(updated, encoding="utf-8")
    return updated


def render_turn_prompt(turn: MiniMaxTurnPrompt) -> str:
    lines = [
        "[牌局元信息]",
        "room_id: {}".format(turn.room_id),
        "hand_id: {}".format(turn.hand_id),
        "bot_id: {}".format(turn.bot_id),
        "",
        "[当前牌面信息]",
        "phase: {}".format(turn.phase),
        "hero_seat: {}".format(turn.hero_seat),
        "hero_cards: {}".format(turn.hero_cards),
        "board_cards: {}".format(turn.board_cards),
        "pot: {}".format(turn.pot),
        "current_bet: {}".format(turn.current_bet),
        "min_raise: {}".format(turn.min_raise),
        "to_call: {}".format(turn.to_call),
        "chips: {}".format(turn.chips),
        "committed: {}".format(turn.committed),
        "legal_actions: {}".format(", ".join(turn.legal_actions) if turn.legal_actions else "-"),
        "",
        "[之前所有人的操作信息]",
    ]
    if turn.action_history:
        for index, action in enumerate(turn.action_history, start=1):
            lines.append("{}. {}".format(index, action))
    else:
        lines.append("1. 无公开操作")
    return "\n".join(lines)
