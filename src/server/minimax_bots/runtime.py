from __future__ import annotations

from dataclasses import dataclass
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


def fallback_decision(legal_actions: tuple[str, ...], *, reason: str, transcript_path: str = "", raw_response: str = "") -> MiniMaxBotDecision:
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


def parse_decision(response_text: str, legal_actions: tuple[str, ...], transcript_path: str = "") -> MiniMaxBotDecision:
    move_match = re.search(r"^move_type:\s*([A-Z_]+)\s*$", response_text, flags=re.MULTILINE)
    amount_match = re.search(r"^amount:\s*(-?\d+)\s*$", response_text, flags=re.MULTILINE)
    reason_match = re.search(r"^reason:\s*(.+?)\s*$", response_text, flags=re.MULTILINE)
    if not move_match:
        return fallback_decision(legal_actions, reason="Model response missing move_type.", transcript_path=transcript_path, raw_response=response_text)

    move_type = move_match.group(1).strip().upper()
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

    amount = int(amount_match.group(1)) if amount_match else 0
    if move_type != "RAISE":
        amount = 0
    if move_type == "RAISE" and amount <= 0:
        return fallback_decision(
            legal_actions,
            reason="Model response omitted a valid raise amount.",
            transcript_path=transcript_path,
            raw_response=response_text,
        )
    reason = reason_match.group(1).strip() if reason_match else ""
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
    max_tokens: int = 2048,
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
                "你必须严格根据用户提供的牌局信息做决策。"
                "你必须严格使用固定模板输出，不能添加模板外说明。"
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
