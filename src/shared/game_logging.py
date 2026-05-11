from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import uuid


def generate_hand_id(room_id: str, hand_number: int) -> str:
    safe_room = sanitize_name(room_id) or "room"
    return f"{safe_room}-{hand_number:06d}-{uuid.uuid4().hex[:8]}"


def sanitize_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value.strip())
    return cleaned.strip("_")


@dataclass(frozen=True)
class LogRecord:
    timestamp: str
    scope: str
    owner_id: str
    room_id: str
    hand_id: str
    hand_number: int
    phase: str
    event_type: str
    message: str
    data: dict[str, object]


class GameLogStore:
    def __init__(self, root_dir: str | Path, scope: str, owner_id: str) -> None:
        self.root_dir = Path(root_dir)
        self.scope = sanitize_name(scope) or "logs"
        self.owner_id = sanitize_name(owner_id) or "anonymous"
        self._lock = threading.Lock()

    def with_owner(self, owner_id: str) -> "GameLogStore":
        return GameLogStore(self.root_dir, self.scope, owner_id)

    def room_dir(self, room_id: str) -> Path:
        safe_room = sanitize_name(room_id) or "room"
        return self.root_dir / self.scope / self.owner_id / safe_room

    def room_log_path(self, room_id: str) -> Path:
        return self.room_dir(room_id) / "room.log"

    def hand_log_path(self, room_id: str, hand_number: int, hand_id: str) -> Path:
        safe_hand = sanitize_name(hand_id) or f"hand_{hand_number:06d}"
        return self.room_dir(room_id) / "hands" / f"{hand_number:06d}_{safe_hand}.log"

    def hand_log_jsonl_path(self, room_id: str, hand_number: int, hand_id: str) -> Path:
        return self.hand_log_path(room_id, hand_number, hand_id).with_suffix(".jsonl")

    def find_hand_log_jsonl(self, room_id: str, hand_id: str) -> Path | None:
        hands_dir = self.room_dir(room_id) / "hands"
        if not hands_dir.exists():
            return None
        safe_hand = sanitize_name(hand_id)
        matches = sorted(hands_dir.glob(f"*_{safe_hand}.jsonl"))
        return matches[-1] if matches else None

    def write(
        self,
        room_id: str,
        message: str,
        *,
        phase: str,
        event_type: str,
        hand_id: str = "",
        hand_number: int = 0,
        data: dict[str, object] | None = None,
    ) -> None:
        payload = data or {}
        record = LogRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            scope=self.scope,
            owner_id=self.owner_id,
            room_id=room_id,
            hand_id=hand_id,
            hand_number=hand_number,
            phase=phase,
            event_type=event_type,
            message=message,
            data=payload,
        )
        room_path = self.room_log_path(room_id)
        room_path.parent.mkdir(parents=True, exist_ok=True)
        line = self.format_line(record)
        json_line = json.dumps(record.__dict__, ensure_ascii=False)

        with self._lock:
            with room_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            with room_path.with_suffix(".jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json_line + "\n")
            if hand_id:
                hand_path = self.hand_log_path(room_id, hand_number, hand_id)
                hand_path.parent.mkdir(parents=True, exist_ok=True)
                with hand_path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
                with self.hand_log_jsonl_path(room_id, hand_number, hand_id).open("a", encoding="utf-8") as handle:
                    handle.write(json_line + "\n")

    def recent_lines(self, room_id: str, limit: int = 20) -> list[str]:
        path = self.room_log_path(room_id)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        return [line.rstrip("\n") for line in lines[-limit:]]

    def format_line(self, record: LogRecord) -> str:
        prefix = [
            record.timestamp,
            record.phase or "NA",
            record.event_type or "EVENT",
        ]
        if record.hand_id:
            prefix.append(record.hand_id)
        line = f"[{' | '.join(prefix)}] {record.message}"
        if record.data:
            line += f" {json.dumps(record.data, ensure_ascii=False, sort_keys=True)}"
        return line
