from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


INPUT_START = "<!-- MINIMAX_BOT_INPUT_START -->"
INPUT_END = "<!-- MINIMAX_BOT_INPUT_END -->"
OUTPUT_START = "<!-- MINIMAX_BOT_OUTPUT_START -->"
OUTPUT_END = "<!-- MINIMAX_BOT_OUTPUT_END -->"


SYSTEM_PROMPT = """你是一个非交互式德州扑克牌局机器人。
你必须严格根据用户提供的牌局信息做决策。
你必须严格使用下面的固定模板输出，不能添加模板外的说明，不能省略任何字段。

[当前牌面信息]
phase: <阶段>
hero_seat: <你的座位号，从1开始>
hero_cards: <你的手牌，未知时写 ->
board_cards: <公共牌，没有时写 ->
pot: <底池整数>
current_bet: <当前下注整数>
min_raise: <最小加注整数>
to_call: <当前需要跟注整数>
chips: <你剩余筹码整数>
committed: <你本轮已投入整数>
legal_actions: <可行动作，逗号分隔>

[之前所有人的操作信息]
1. <第1条操作>
2. <第2条操作>

[机器人决策]
move_type: <FOLD|CHECK|CALL|RAISE|ALL_IN>
amount: <整数；非RAISE时填0>
reason: <一句中文理由>
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
