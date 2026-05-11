from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from src.shared.game_logging import GameLogStore, LogRecord


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


@dataclass(frozen=True)
class HandReplay:
    path: Path
    records: tuple[LogRecord, ...]


def load_hand_replay(
    store: GameLogStore,
    *,
    room_id: str,
    hand_id: str | None = None,
    hand_number: int | None = None,
    path: str | Path | None = None,
) -> HandReplay:
    if path is not None:
        replay_path = Path(path)
    elif hand_number is not None and hand_id is not None:
        replay_path = store.hand_log_jsonl_path(room_id, hand_number, hand_id)
    elif hand_id is not None:
        replay_path = store.find_hand_log_jsonl(room_id, hand_id) or Path()
    else:
        raise ValueError("hand_id or path is required")

    if not replay_path.exists():
        raise FileNotFoundError(f"Hand replay log not found: {replay_path}")
    return HandReplay(path=replay_path, records=tuple(read_log_records(replay_path)))


def read_log_records(path: str | Path) -> list[LogRecord]:
    records: list[LogRecord] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            records.append(
                LogRecord(
                    timestamp=payload.get("timestamp", ""),
                    scope=payload.get("scope", ""),
                    owner_id=payload.get("owner_id", ""),
                    room_id=payload.get("room_id", ""),
                    hand_id=payload.get("hand_id", ""),
                    hand_number=payload.get("hand_number", 0),
                    phase=payload.get("phase", ""),
                    event_type=payload.get("event_type", ""),
                    message=payload.get("message", ""),
                    data=payload.get("data", {}),
                )
            )
    return records


def render_hand_replay(replay: HandReplay) -> str:
    if not replay.records:
        return "No replay records found."

    first = replay.records[0]
    lines = [
        f"Hand {first.hand_number} replay",
        f"room_id={first.room_id}",
        f"hand_id={first.hand_id}",
        f"log={replay.path}",
        "",
    ]
    for record in replay.records:
        lines.append(render_record(record))
    return "\n".join(lines)


def render_record(record: LogRecord) -> str:
    prefix = f"{record.phase:>13} | {record.event_type:<12}"
    if record.event_type == "HAND_START":
        return f"{prefix} {render_hand_start(record)}"
    if record.event_type == "ACTION":
        return f"{prefix} {render_action(record)}"
    if record.event_type == "STREET":
        return f"{prefix} {record.message}: board={format_cards(record.data.get('board', []))}"
    if record.event_type == "BOT_DECISION":
        return f"{prefix} {render_bot_decision(record)}"
    if record.event_type == "HAND_END":
        return f"{prefix} {render_hand_end(record)}"
    if record.event_type == "RESULT":
        return f"{prefix} {render_result(record)}"
    return f"{prefix} {record.message}"


def render_hand_start(record: LogRecord) -> str:
    seats = record.data.get("seats", [])
    seat_chunks = []
    for seat in seats:
        seat_chunks.append(
            f"S{seat['seat_index'] + 1} {seat['name']} stack={seat['chips']} hole={format_cards(seat.get('hole_cards', []))}"
        )
    return (
        f"{record.message} dealer=S{record.data.get('dealer_seat', -1) + 1} "
        f"sb=S{record.data.get('small_blind_seat', -1) + 1}/{record.data.get('small_blind_amount', 0)} "
        f"bb=S{record.data.get('big_blind_seat', -1) + 1}/{record.data.get('big_blind_amount', 0)} "
        + " | ".join(seat_chunks)
    )


def render_action(record: LogRecord) -> str:
    data = record.data
    amount = data.get("amount", 0)
    amount_text = f" to {amount}" if amount else ""
    return (
        f"S{data.get('seat_index', -1) + 1} {data.get('player_name', data.get('player_id', ''))} "
        f"{data.get('move_type', '')}{amount_text} "
        f"(put_in={data.get('chips_put_in', 0)}, to_call={data.get('to_call_before', 0)}, "
        f"pot {data.get('pot_before', 0)}->{data.get('pot_after', 0)})"
    )


def render_bot_decision(record: LogRecord) -> str:
    decision = record.data.get("decision", {})
    move_type = decision.get("move_type", "")
    amount = decision.get("amount", 0)
    reason = record.data.get("reason", "")
    amount_text = f" to {amount}" if amount else ""
    return f"{record.message}: {move_type}{amount_text} reason={reason}"


def render_result(record: LogRecord) -> str:
    data = record.data
    if "hand_name" in data:
        return (
            f"{record.message} board={format_cards(data.get('board', []))} "
            f"winner=S{data.get('winner_seat', -1) + 1}"
        )
    if "amount" in data:
        return (
            f"{record.message} board={format_cards(data.get('board', []))} "
            f"winner=S{data.get('winner_seat', -1) + 1} amount={data.get('amount', 0)}"
        )
    return record.message


def render_hand_end(record: LogRecord) -> str:
    winners = ", ".join(f"S{seat + 1}" for seat in record.data.get("winners", [])) or "-"
    board = format_cards(record.data.get("board", []))
    deltas = record.data.get("chip_deltas", {})
    delta_text = ", ".join(f"S{int(seat) + 1}:{delta:+d}" for seat, delta in sorted(deltas.items(), key=lambda item: int(item[0])))
    return f"{record.message} winners={winners} board={board} deltas=[{delta_text}]"


def format_cards(cards: list[dict[str, str]]) -> str:
    if not cards:
        return "-"
    return " ".join(f"{RANK_LABELS.get(card.get('rank', ''), '?')}{SUIT_LABELS.get(card.get('suit', ''), '?')}" for card in cards)
