from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import sys
import time
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


from src.client.network import PokerClientConnection
from src.proto_gen import poker_pb2
from src.server.grpc_service import BOT_PREFIX, MINIMAX_BOT_PREFIX
from src.shared.game_logging import GameLogStore


@dataclass(frozen=True)
class MatchPlayer:
    player_id: str
    name: str
    seat_index: int


@dataclass(frozen=True)
class MiniMaxDecisionRecord:
    hand_id: str
    move_type: str
    amount: int
    source: str
    reason: str
    transcript_path: str
    raw_response: str


@dataclass(frozen=True)
class HandMatchRecord:
    hand_id: str
    hand_number: int
    winner_seats: tuple[int, ...]
    chip_deltas: dict[int, int]
    final_stacks: dict[int, int]
    action_counts: dict[str, Counter[str]]


class RemoteMatchSession:
    def __init__(self, address: str, *, poll_interval: float = 0.2) -> None:
        self.connection = PokerClientConnection(address)
        self.poll_interval = poll_interval
        self.player_id = ""
        self.room_id = ""
        self.snapshot: poker_pb2.RoomSnapshot | None = None
        self.errors: list[str] = []
        self._hand_results: dict[str, poker_pb2.HandResult] = {}

    def send(self, event: poker_pb2.ClientEvent) -> None:
        self.connection.send(event)

    def login(self, name: str, avatar_id: str = "mint") -> None:
        self.send(poker_pb2.ClientEvent(login=poker_pb2.Login(name=name, avatar_id=avatar_id)))
        self.wait_for(lambda: bool(self.player_id), timeout=15.0, description="login to be accepted")

    def create_room(self, display_name: str) -> None:
        self.send(poker_pb2.ClientEvent(create_room=poker_pb2.CreateRoom(display_name=display_name)))
        self.wait_for(
            lambda: bool(self.room_id) and self.snapshot is not None and self.snapshot.room_id == self.room_id,
            timeout=15.0,
            description="room to be created",
        )

    def leave_room(self) -> None:
        self.send(poker_pb2.ClientEvent(leave_room=poker_pb2.LeaveRoom()))
        self.wait_for(
            lambda: self.snapshot is None or self.snapshot.room_id != self.room_id,
            timeout=10.0,
            description="room to be left",
        )

    def add_guarded_bot(self) -> None:
        self.send(poker_pb2.ClientEvent(chat_message=poker_pb2.ChatMessage(text="/addbot")))

    def add_minimax_bot(self) -> None:
        self.send(poker_pb2.ClientEvent(chat_message=poker_pb2.ChatMessage(text="/addminimaxbot")))

    def start_hand(self) -> None:
        self.send(poker_pb2.ClientEvent(start_hand=poker_pb2.StartHand()))

    def room_players(self) -> dict[str, MatchPlayer]:
        players: dict[str, MatchPlayer] = {}
        if not self.snapshot:
            return players
        names = {member.player_id: member.name for member in self.snapshot.members}
        for seat in self.snapshot.seats:
            if seat.player_id:
                players[seat.player_id] = MatchPlayer(
                    player_id=seat.player_id,
                    name=seat.name or names.get(seat.player_id, seat.player_id),
                    seat_index=seat.seat_index,
                )
        return players

    def wait_for(self, predicate: Callable[[], bool], *, timeout: float, description: str) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._drain_events()
            if self.errors:
                raise RuntimeError(self.errors[-1])
            if predicate():
                return
            time.sleep(self.poll_interval)
        raise TimeoutError(f"Timed out waiting for {description}.")

    def _drain_events(self) -> None:
        for event in self.connection.poll():
            payload = event.WhichOneof("payload")
            if payload == "login_accepted":
                self.player_id = event.login_accepted.player_id
                self.connection.set_identity(event.login_accepted.player_id, event.login_accepted.reconnect_token)
            elif payload == "joined":
                self.room_id = event.joined.room_id
            elif payload == "snapshot":
                self.snapshot = event.snapshot
                if event.snapshot.last_hand_result.hand_id:
                    self._hand_results[event.snapshot.last_hand_result.hand_id] = event.snapshot.last_hand_result
            elif payload == "hand_result":
                self._hand_results[event.hand_result.hand_id] = event.hand_result
            elif payload == "error":
                message = event.error.message or event.error.code or "Unknown server error"
                self.errors.append(message)

    def wait_for_bots(self) -> tuple[MatchPlayer, MatchPlayer]:
        self.wait_for(
            lambda: self._bot_count(BOT_PREFIX) >= 1 and self._bot_count(MINIMAX_BOT_PREFIX) >= 1,
            timeout=20.0,
            description="score bot and minimax bot to join",
        )
        players = self.room_players()
        score = next(player for player in players.values() if player.player_id.startswith(BOT_PREFIX))
        minimax = next(player for player in players.values() if player.player_id.startswith(MINIMAX_BOT_PREFIX))
        return score, minimax

    def _bot_count(self, prefix: str) -> int:
        return sum(1 for player_id in self.room_players() if player_id.startswith(prefix))

    def run_hand(self, timeout: float) -> poker_pb2.HandResult:
        seen = set(self._hand_results)
        self.wait_for(
            lambda: self.snapshot is not None
            and self.snapshot.room_status == poker_pb2.OPEN
            and self.snapshot.phase in (poker_pb2.WAITING, poker_pb2.HAND_COMPLETE),
            timeout=20.0,
            description="room to become startable",
        )
        self.start_hand()
        self.wait_for(
            lambda: any(hand_id not in seen for hand_id in self._hand_results),
            timeout=timeout,
            description="hand result",
        )
        new_hand_id = next(hand_id for hand_id in self._hand_results if hand_id not in seen)
        return self._hand_results[new_hand_id]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a live guarded-bot vs MiniMax-bot match against a gRPC server.")
    parser.add_argument("--address", default="127.0.0.1:50051", help="Target gRPC server address.")
    parser.add_argument("--hands", type=int, default=3, help="Number of hands to play.")
    parser.add_argument("--timeout", type=float, default=90.0, help="Per-hand timeout in seconds.")
    parser.add_argument("--poll-interval", type=float, default=0.2, help="Polling interval for the gRPC stream.")
    parser.add_argument("--owner-name", default="LLM Match Driver", help="Name used for the driver account.")
    parser.add_argument("--room-name", default="Remote LLM Bot Match", help="Display name for the temporary room.")
    parser.add_argument("--logs-root", default="runtime_logs", help="Root directory that contains server runtime logs.")
    parser.add_argument("--transcript-limit", type=int, default=3, help="How many recent MiniMax transcripts to print.")
    parser.add_argument("--json", action="store_true", help="Print a JSON report after the text summary.")
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def collect_hand_action_counts(
    store: GameLogStore,
    room_id: str,
    hand_ids: list[str],
) -> dict[str, Counter[str]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for hand_id in hand_ids:
        hand_path = store.find_hand_log_jsonl(room_id, hand_id)
        if not hand_path:
            continue
        for row in read_jsonl(hand_path):
            if row.get("event_type") != "ACTION":
                continue
            data = row.get("data", {})
            if not isinstance(data, dict):
                continue
            player_id = str(data.get("player_id", ""))
            move_type = str(data.get("move_type", ""))
            if player_id and move_type:
                counts[player_id][move_type] += 1
    return dict(counts)


def collect_minimax_decisions(
    store: GameLogStore,
    room_id: str,
    hand_ids: list[str],
) -> list[MiniMaxDecisionRecord]:
    room_jsonl = store.room_log_path(room_id).with_suffix(".jsonl")
    rows = read_jsonl(room_jsonl)
    hand_id_set = set(hand_ids)
    decisions: list[MiniMaxDecisionRecord] = []
    for row in rows:
        if row.get("event_type") != "MINIMAX_BOT_DECISION":
            continue
        hand_id = str(row.get("hand_id", ""))
        if hand_id not in hand_id_set:
            continue
        data = row.get("data", {})
        if not isinstance(data, dict):
            continue
        decision = data.get("decision", {})
        if not isinstance(decision, dict):
            decision = {}
        decisions.append(
            MiniMaxDecisionRecord(
                hand_id=hand_id,
                move_type=str(decision.get("move_type", "")),
                amount=int(decision.get("amount", 0) or 0),
                source=str(data.get("source", "")),
                reason=str(data.get("reason", "")),
                transcript_path=str(data.get("transcript_path", "")),
                raw_response=str(data.get("raw_response", "")),
            )
        )
    return decisions


def action_rates(counter: Counter[str]) -> dict[str, float]:
    total = sum(counter.values())
    if total <= 0:
        return {"fold_rate": 0.0, "check_rate": 0.0, "call_rate": 0.0, "raise_rate": 0.0, "all_in_rate": 0.0}
    return {
        "fold_rate": counter.get("FOLD", 0) / total,
        "check_rate": counter.get("CHECK", 0) / total,
        "call_rate": counter.get("CALL", 0) / total,
        "raise_rate": counter.get("RAISE", 0) / total,
        "all_in_rate": counter.get("ALL_IN", 0) / total,
    }


def build_hand_record(
    hand_result: poker_pb2.HandResult,
    action_counts: dict[str, Counter[str]],
    players_by_seat: dict[int, MatchPlayer],
) -> HandMatchRecord:
    return HandMatchRecord(
        hand_id=hand_result.hand_id,
        hand_number=hand_result.hand_number,
        winner_seats=tuple(hand_result.winner_seats),
        chip_deltas={delta.seat_index: delta.delta for delta in hand_result.chip_deltas},
        final_stacks={delta.seat_index: delta.final_stack for delta in hand_result.chip_deltas},
        action_counts={
            players_by_seat[seat_index].player_id: action_counts.get(players_by_seat[seat_index].player_id, Counter())
            for seat_index in players_by_seat
        },
    )


def render_summary(
    hands: list[HandMatchRecord],
    players: list[MatchPlayer],
    minimax_decisions: list[MiniMaxDecisionRecord],
    transcript_limit: int,
) -> str:
    player_by_id = {player.player_id: player for player in players}
    lines = [f"Remote bot match over {len(hands)} hands", ""]
    totals = Counter[str]()
    wins = Counter[str]()
    action_totals: dict[str, Counter[str]] = defaultdict(Counter)

    for hand in hands:
        winner_names = ", ".join(player_by_id[player_id].name for player_id in player_by_id if player_by_id[player_id].seat_index in hand.winner_seats)
        lines.append(f"Hand {hand.hand_number} | {hand.hand_id}")
        lines.append(f"  winners={winner_names or '-'}")
        deltas = []
        for player in players:
            delta = hand.chip_deltas.get(player.seat_index, 0)
            totals[player.player_id] += delta
            if player.seat_index in hand.winner_seats:
                wins[player.player_id] += 1
            deltas.append(f"{player.name}:{delta:+d}")
            action_totals[player.player_id].update(hand.action_counts.get(player.player_id, Counter()))
        lines.append(f"  chip_deltas={' '.join(deltas)}")
        lines.append("")

    for player in players:
        rates = action_rates(action_totals[player.player_id])
        lines.append(f"{player.player_id} ({player.name})")
        lines.append(f"  chip_delta={totals[player.player_id]:+d} wins={wins[player.player_id]}")
        lines.append(
            "  actions="
            f"fold:{action_totals[player.player_id].get('FOLD', 0)} "
            f"check:{action_totals[player.player_id].get('CHECK', 0)} "
            f"call:{action_totals[player.player_id].get('CALL', 0)} "
            f"raise:{action_totals[player.player_id].get('RAISE', 0)} "
            f"all_in:{action_totals[player.player_id].get('ALL_IN', 0)}"
        )
        lines.append(
            "  rates="
            f"fold:{rates['fold_rate']:.3f} check:{rates['check_rate']:.3f} call:{rates['call_rate']:.3f} "
            f"raise:{rates['raise_rate']:.3f} all_in:{rates['all_in_rate']:.3f}"
        )
        lines.append("")

    source_counts = Counter(decision.source for decision in minimax_decisions)
    lines.append("MiniMax decisions")
    lines.append(
        f"  total={len(minimax_decisions)} model={source_counts.get('model', 0)} fallback={source_counts.get('fallback', 0)}"
    )
    for decision in minimax_decisions[-transcript_limit:]:
        suffix = f" amount={decision.amount}" if decision.amount else ""
        lines.append(
            f"  {decision.hand_id} | {decision.source} | {decision.move_type}{suffix} | {decision.transcript_path}"
        )
        if decision.reason:
            lines.append(f"    reason={decision.reason}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    session = RemoteMatchSession(args.address, poll_interval=args.poll_interval)
    session.login(args.owner_name)

    hand_results: list[poker_pb2.HandResult] = []
    players: list[MatchPlayer] = []
    for hand_index in range(args.hands):
        session.create_room(f"{args.room_name} #{hand_index + 1}")
        session.add_guarded_bot()
        session.add_minimax_bot()
        score_bot, minimax_bot = session.wait_for_bots()
        if not players:
            players = [score_bot, minimax_bot]
        hand_result = session.run_hand(args.timeout)
        hand_results.append(hand_result)
        session.wait_for(
            lambda: session.snapshot is not None and session.snapshot.room_status == poker_pb2.OPEN,
            timeout=15.0,
            description="room to reopen after the hand",
        )
        if any(delta.final_stack <= 0 for delta in hand_result.chip_deltas):
            session.leave_room()
            break
        session.leave_room()

    hand_records: list[HandMatchRecord] = []
    all_decisions: list[MiniMaxDecisionRecord] = []
    players_by_seat = {player.seat_index: player for player in players}
    for result in hand_results:
        room_id = result.hand_id.split("-000001-")[0]
        store = GameLogStore(Path(args.logs_root), "server", room_id)
        action_counts = collect_hand_action_counts(store, room_id, [result.hand_id])
        all_decisions.extend(collect_minimax_decisions(store, room_id, [result.hand_id]))
        hand_records.append(build_hand_record(result, action_counts, players_by_seat))

    print(render_summary(hand_records, players, all_decisions, args.transcript_limit))

    if args.json:
        payload = {
            "address": args.address,
            "players": [player.__dict__ for player in players],
            "hands": [
                {
                    "hand_id": hand.hand_id,
                    "hand_number": hand.hand_number,
                    "winner_seats": list(hand.winner_seats),
                    "chip_deltas": hand.chip_deltas,
                    "final_stacks": hand.final_stacks,
                    "action_counts": {player_id: dict(counter) for player_id, counter in hand.action_counts.items()},
                }
                for hand in hand_records
            ],
            "minimax_decisions": [decision.__dict__ for decision in all_decisions],
        }
        print()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
