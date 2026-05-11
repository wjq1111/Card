from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from src.server.room import BIG_BLIND, SMALL_BLIND, Phase, PokerRoom, Seat
from src.server.minimax_bots.document_io import (
    INPUT_END,
    INPUT_START,
    OUTPUT_END,
    OUTPUT_START,
    MiniMaxTurnPrompt,
    render_turn_prompt,
    write_bot_output,
)
from src.server.minimax_bots.minimax_client import combined_text_blocks, create_message, read_api_key


RANK_LABELS = {
    "TWO": "2",
    "THREE": "3",
    "FOUR": "4",
    "FIVE": "5",
    "SIX": "6",
    "SEVEN": "7",
    "EIGHT": "8",
    "NINE": "9",
    "TEN": "T",
    "JACK": "J",
    "QUEEN": "Q",
    "KING": "K",
    "ACE": "A",
}
SUIT_LABELS = {
    "CLUBS": "c",
    "DIAMONDS": "d",
    "HEARTS": "h",
    "SPADES": "s",
}
MOVE_TYPES = {"FOLD", "CHECK", "CALL", "RAISE", "ALL_IN"}
MOVE_ALIASES = {
    "FOLD": "FOLD",
    "CHECK": "CHECK",
    "CALL": "CALL",
    "RAISE": "RAISE",
    "BET": "RAISE",
    "ALL_IN": "ALL_IN",
    "ALLIN": "ALL_IN",
    "弃牌": "FOLD",
    "过牌": "CHECK",
    "跟注": "CALL",
    "加注": "RAISE",
    "下注": "RAISE",
    "全下": "ALL_IN",
}


@dataclass(frozen=True)
class MiniMaxBotDecision:
    move_type: str
    amount: int = 0
    reason: str = ""
    source: str = "model"
    transcript_path: str = ""
    raw_response: str = ""


def legal_actions_for_seat(room: PokerRoom, seat: Seat) -> tuple[str, ...]:
    if room.phase in (Phase.WAITING, Phase.HAND_COMPLETE) or seat.seat_index != room.active_seat:
        return ()

    actions: list[str] = []
    to_call = max(0, room.current_bet - seat.committed)
    if to_call > 0:
        actions.append("FOLD")
        if seat.chips > 0:
            actions.append("CALL")
    else:
        actions.append("CHECK")

    can_full_raise = seat.committed + seat.chips >= room.current_bet + room.min_raise
    if can_full_raise and seat.chips > to_call:
        actions.append("RAISE")
    if seat.chips > 0:
        actions.append("ALL_IN")
    return tuple(actions)


def format_cards(cards) -> str:
    if not cards:
        return "-"
    return " ".join("{}{}".format(RANK_LABELS.get(card.rank, "?"), SUIT_LABELS.get(card.suit, "?")) for card in cards)


def build_action_history(room: PokerRoom) -> tuple[str, ...]:
    actions: list[str] = []
    active = [seat for seat in room.seats if seat.player_id and seat.hole_cards]
    if room.phase != Phase.WAITING and active and room.dealer_seat >= 0:
        small_blind_seat, big_blind_seat = room.blind_seats(active)
        small_blind = room.seats[small_blind_seat]
        big_blind = room.seats[big_blind_seat]
        actions.append(
            "PREFLOP | S{} {} | SMALL_BLIND | amount={}".format(
                small_blind.seat_index + 1,
                small_blind.name,
                SMALL_BLIND,
            )
        )
        actions.append(
            "PREFLOP | S{} {} | BIG_BLIND | amount={}".format(
                big_blind.seat_index + 1,
                big_blind.name,
                BIG_BLIND,
            )
        )
    for record in room.hand_action_log:
        player_name = room.players.get(record.player_id, record.player_id)
        actions.append(
            "{} | S{} {} | {} | amount={}".format(
                record.phase,
                record.seat_index + 1,
                player_name,
                record.move_type,
                record.amount,
            )
        )
    return tuple(actions)


def build_turn_prompt(room: PokerRoom, player_id: str) -> MiniMaxTurnPrompt:
    seat = room.require_seat(player_id)
    to_call = max(0, room.current_bet - seat.committed)
    return MiniMaxTurnPrompt(
        room_id=room.room_id,
        hand_id=room.current_hand_id,
        bot_id=player_id,
        phase=room.phase.value,
        hero_seat=seat.seat_index + 1,
        hero_cards=format_cards(seat.hole_cards),
        board_cards=format_cards(room.board),
        pot=room.pot,
        current_bet=room.current_bet,
        min_raise=room.min_raise,
        to_call=to_call,
        chips=seat.chips,
        committed=seat.committed,
        legal_actions=legal_actions_for_seat(room, seat),
        action_history=build_action_history(room),
    )


def turn_document_text(prompt: MiniMaxTurnPrompt, *, output_text: str = "pending") -> str:
    return "\n".join(
        [
            "# MiniMax Bot Turn",
            "",
            INPUT_START,
            render_turn_prompt(prompt),
            INPUT_END,
            "",
            OUTPUT_START,
            output_text,
            OUTPUT_END,
            "",
        ]
    )


def transcript_path_for_turn(root_dir: str | Path, room: PokerRoom, player_id: str) -> Path:
    turn_index = 1 + sum(1 for record in room.hand_action_log if record.player_id == player_id)
    safe_player = player_id.replace(":", "_")
    hand_dir = "{}_{}".format(room.hand_number, room.current_hand_id)
    return Path(root_dir) / room.room_id / hand_dir / safe_player / "turn_{:03d}.md".format(turn_index)


def fallback_decision(
    legal_actions: tuple[str, ...],
    *,
    reason: str,
    transcript_path: str = "",
    raw_response: str = "",
) -> MiniMaxBotDecision:
    legal = set(legal_actions)
    if "CHECK" in legal:
        return MiniMaxBotDecision("CHECK", reason=reason, source="fallback", transcript_path=transcript_path, raw_response=raw_response)
    if "CALL" in legal:
        return MiniMaxBotDecision("CALL", reason=reason, source="fallback", transcript_path=transcript_path, raw_response=raw_response)
    if "FOLD" in legal:
        return MiniMaxBotDecision("FOLD", reason=reason, source="fallback", transcript_path=transcript_path, raw_response=raw_response)
    if "ALL_IN" in legal:
        return MiniMaxBotDecision("ALL_IN", reason=reason, source="fallback", transcript_path=transcript_path, raw_response=raw_response)
    raise ValueError("No legal fallback action is available.")


def _normalize_move_type(value: str) -> str:
    cleaned = value.strip().strip("*`_#[](){}<>.,，。:：;；!！?？\"'").upper().replace("-", "_").replace(" ", "_")
    if cleaned in MOVE_ALIASES:
        return MOVE_ALIASES[cleaned]
    return MOVE_ALIASES.get(value.strip(), cleaned)


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+", value)
        if match:
            return int(match.group(0))
    return None


def _extract_json_payload(response_text: str) -> tuple[str, int | None, str]:
    candidates: list[str] = []
    candidates.extend(re.findall(r"```(?:json)?\s*(.*?)```", response_text, flags=re.DOTALL | re.IGNORECASE))
    candidates.extend(re.findall(r"(\{.*?\}|\[.*?\])", response_text, flags=re.DOTALL))
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            payload = payload[0]
        if not isinstance(payload, dict):
            continue
        return (
            _normalize_move_type(str(payload.get("move_type") or payload.get("action") or payload.get("decision") or "")),
            _coerce_int(payload.get("amount")),
            str(payload.get("reason") or payload.get("reasoning") or payload.get("explanation") or "").strip(),
        )
    return "", None, ""


def _extract_labeled_payload(response_text: str) -> tuple[str, int | None, str]:
    move_patterns = [
        r"(?:move_type|action|final_action|动作|行动|最终行动|决策结果|决策)\s*[:：]\s*([A-Za-z_\u4e00-\u9fff]+)",
        r"\*\*(?:动作|行动|最终行动|决策结果|决策)\*\*\s*[:：]?\s*([A-Za-z_\u4e00-\u9fff]+)",
    ]
    move_type = ""
    for pattern in move_patterns:
        match = re.search(pattern, response_text, flags=re.IGNORECASE)
        if match:
            move_type = _normalize_move_type(match.group(1))
            break
    amount = None
    for pattern in (r"(?:amount|加注金额|下注金额|raise_amount)\s*[:：]\s*(-?\d+)",):
        match = re.search(pattern, response_text, flags=re.IGNORECASE)
        if match:
            amount = int(match.group(1))
            break
    reason = ""
    reason_match = re.search(r"(?:reason|理由|原因)\s*[:：]\s*(.+)", response_text, flags=re.IGNORECASE)
    if reason_match:
        reason = reason_match.group(1).strip()
    return move_type, amount, reason


def _extract_structured_payload(response_text: str) -> tuple[str, int | None, str]:
    move_match = re.search(r"^move_type:\s*([^\n]+?)\s*$", response_text, flags=re.MULTILINE | re.IGNORECASE)
    amount_match = re.search(r"^amount:\s*(-?\d+)\s*$", response_text, flags=re.MULTILINE | re.IGNORECASE)
    reason_match = re.search(r"^reason:\s*(.+?)\s*$", response_text, flags=re.MULTILINE | re.IGNORECASE)
    if not move_match:
        return "", None, ""
    return (
        _normalize_move_type(move_match.group(1)),
        int(amount_match.group(1)) if amount_match else None,
        reason_match.group(1).strip() if reason_match else "",
    )


def _extract_bare_move(response_text: str) -> str:
    stripped = response_text.strip()
    if "\n" not in stripped and len(stripped) <= 32:
        normalized = _normalize_move_type(stripped)
        if normalized in MOVE_TYPES:
            return normalized
    return ""


def _extract_three_line_payload(response_text: str) -> tuple[str, int | None, str]:
    lines = [line.strip() for line in response_text.splitlines() if line.strip()]
    if len(lines) < 2 or len(lines) > 4:
        return "", None, ""
    move_type = _normalize_move_type(lines[0])
    if move_type not in MOVE_TYPES:
        return "", None, ""
    amount = _coerce_int(lines[1])
    reason = lines[2] if len(lines) >= 3 else ""
    return move_type, amount, reason


def parse_decision(response_text: str, legal_actions: tuple[str, ...], transcript_path: str = "") -> MiniMaxBotDecision:
    move_type, amount, reason = _extract_structured_payload(response_text)
    if not move_type:
        move_type, amount, reason = _extract_json_payload(response_text)
    if not move_type:
        move_type, amount, reason = _extract_labeled_payload(response_text)
    if not move_type:
        move_type, amount, reason = _extract_three_line_payload(response_text)
    if not move_type:
        move_type = _extract_bare_move(response_text)
    if not move_type:
        return fallback_decision(legal_actions, reason="Model response missing move_type.", transcript_path=transcript_path, raw_response=response_text)

    if move_type not in MOVE_TYPES:
        return fallback_decision(
            legal_actions,
            reason="Model response returned unsupported move_type {}.".format(move_type),
            transcript_path=transcript_path,
            raw_response=response_text,
        )
    if move_type not in legal_actions:
        return fallback_decision(
            legal_actions,
            reason="Model response returned illegal move_type {} for the current turn.".format(move_type),
            transcript_path=transcript_path,
            raw_response=response_text,
        )

    amount = 0 if amount is None else amount
    if move_type != "RAISE":
        amount = 0
    if move_type == "RAISE" and amount <= 0:
        return fallback_decision(
            legal_actions,
            reason="Model response omitted a valid raise amount.",
            transcript_path=transcript_path,
            raw_response=response_text,
        )
    if not reason:
        reason = "Parsed from model response."
    return MiniMaxBotDecision(
        move_type=move_type,
        amount=amount,
        reason=reason,
        source="model",
        transcript_path=transcript_path,
        raw_response=response_text,
    )


def run_minimax_bot_turn(
    room: PokerRoom,
    player_id: str,
    *,
    api_key_file: str = "/root/TexasHoldemOnline/api.key",
    transcript_root_dir: str = "runtime_logs/minimax_bots",
    transport: str = "auto",
    max_tokens: int = 1024,
) -> MiniMaxBotDecision:
    prompt = build_turn_prompt(room, player_id)
    transcript_path = transcript_path_for_turn(transcript_root_dir, room, player_id)
    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(turn_document_text(prompt), encoding="utf-8")

    try:
        blocks = create_message(
            api_key=read_api_key(api_key_file),
            system=(
                "你是一个非交互式德州扑克牌局机器人。"
                "你必须严格遵守 legal_actions。"
                "你只能输出三行：move_type、amount、reason。"
                "不要输出 JSON、Markdown、标题或额外解释。"
            ),
            prompt=render_turn_prompt(prompt),
            transport=transport,
            max_tokens=max_tokens,
        )
        response_text = combined_text_blocks(blocks)
    except Exception as exc:
        response_text = "[调用失败]\nerror: {}".format(exc)
        write_bot_output(transcript_path, response_text)
        return fallback_decision(
            prompt.legal_actions,
            reason="MiniMax call failed: {}".format(exc),
            transcript_path=str(transcript_path),
            raw_response=response_text,
        )

    write_bot_output(transcript_path, response_text)
    decision = parse_decision(response_text, prompt.legal_actions, transcript_path=str(transcript_path))
    return MiniMaxBotDecision(
        move_type=decision.move_type,
        amount=decision.amount,
        reason=decision.reason,
        source=decision.source,
        transcript_path=str(transcript_path),
        raw_response=response_text,
    )
