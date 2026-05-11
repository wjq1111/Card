from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
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
    timestamp: str
    player_id: str
    player_name: str
    hand_id: str
    hand_number: int
    move_type: str
    amount: int
    source: str
    reason: str
    transcript_path: str
    raw_response: str


@dataclass(frozen=True)
class GuardedDecisionRecord:
    timestamp: str
    player_id: str
    player_name: str
    hand_id: str
    hand_number: int
    move_type: str
    amount: int
    reason: str
    scores: list[dict[str, object]]
    features: dict[str, object]


@dataclass(frozen=True)
class HandMatchRecord:
    hand_id: str
    hand_number: int
    winner_seats: tuple[int, ...]
    chip_deltas: dict[int, int]
    final_stacks: dict[int, int]
    action_counts: dict[str, Counter[str]]


@dataclass(frozen=True)
class MiniMaxTurnTranscript:
    timestamp: str
    hand_id: str
    hand_number: int
    player_id: str
    player_name: str
    move_type: str
    amount: int
    source: str
    reason: str
    transcript_path: str
    prompt_text: str
    output_text: str
    raw_response: str


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
        try:
            self.wait_for(
                lambda: self.snapshot is None or self.snapshot.room_id != self.room_id,
                timeout=3.0,
                description="room to be left",
            )
        except TimeoutError:
            pass

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

    def wait_for_bot_counts(self, *, guarded_count: int, minimax_count: int) -> list[MatchPlayer]:
        self.wait_for(
            lambda: self._bot_count(BOT_PREFIX) >= guarded_count and self._bot_count(MINIMAX_BOT_PREFIX) >= minimax_count,
            timeout=20.0,
            description="configured bots to join",
        )
        players = list(self.room_players().values())
        players.sort(key=lambda player: player.seat_index)
        return players

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
    parser = argparse.ArgumentParser(description="Run a live bot match against a gRPC server and print MiniMax prompts/results.")
    parser.add_argument("--address", default="127.0.0.1:50051", help="Target gRPC server address.")
    parser.add_argument("--hands", type=int, default=1, help="Number of hands to play in the same room.")
    parser.add_argument("--timeout", type=float, default=90.0, help="Per-hand timeout in seconds.")
    parser.add_argument("--poll-interval", type=float, default=0.2, help="Polling interval for the gRPC stream.")
    parser.add_argument("--owner-name", default="LLM Match Driver", help="Name used for the driver account.")
    parser.add_argument("--room-name", default="Remote LLM Bot Match", help="Display name for the temporary room.")
    parser.add_argument("--logs-root", default="runtime_logs", help="Root directory that contains server runtime logs.")
    parser.add_argument("--guarded-bots", type=int, default=1, help="How many score bots to seat.")
    parser.add_argument("--minimax-bots", type=int, default=1, help="How many MiniMax bots to seat.")
    parser.add_argument("--transcript-limit", type=int, default=0, help="How many recent MiniMax turns to print in the short summary. Use 0 to print all turns.")
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


def read_transcript_sections(path: str) -> tuple[str, str]:
    transcript_path = Path(path)
    if not path or not transcript_path.exists():
        return "", ""
    text = transcript_path.read_text(encoding="utf-8")
    prompt_match = re.search(
        r"<!-- MINIMAX_BOT_INPUT_START -->\n?(.*?)\n?<!-- MINIMAX_BOT_INPUT_END -->",
        text,
        flags=re.DOTALL,
    )
    output_match = re.search(
        r"<!-- MINIMAX_BOT_OUTPUT_START -->\n?(.*?)\n?<!-- MINIMAX_BOT_OUTPUT_END -->",
        text,
        flags=re.DOTALL,
    )
    prompt_text = prompt_match.group(1).strip() if prompt_match else ""
    output_text = output_match.group(1).strip() if output_match else ""
    return prompt_text, output_text


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
                timestamp=str(row.get("timestamp", "")),
                player_id=str(data.get("bot_id", "")),
                player_name=str(row.get("message", "")).split(" minimax bot chose ", 1)[0],
                hand_id=hand_id,
                hand_number=int(row.get("hand_number", 0) or 0),
                move_type=str(decision.get("move_type", "")),
                amount=int(decision.get("amount", 0) or 0),
                source=str(data.get("source", "")),
                reason=str(data.get("reason", "")),
                transcript_path=str(data.get("transcript_path", "")),
                raw_response=str(data.get("raw_response", "")),
            )
        )
    return decisions


def collect_guarded_decisions(
    store: GameLogStore,
    room_id: str,
    hand_ids: list[str],
) -> list[GuardedDecisionRecord]:
    room_jsonl = store.room_log_path(room_id).with_suffix(".jsonl")
    rows = read_jsonl(room_jsonl)
    hand_id_set = set(hand_ids)
    decisions: list[GuardedDecisionRecord] = []
    for row in rows:
        if row.get("event_type") != "BOT_DECISION":
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
        scores = data.get("scores", [])
        if not isinstance(scores, list):
            scores = []
        features = data.get("features", {})
        if not isinstance(features, dict):
            features = {}
        decisions.append(
            GuardedDecisionRecord(
                timestamp=str(row.get("timestamp", "")),
                player_id=str(data.get("bot_id", "")),
                player_name=str(row.get("message", "")).split(" bot chose ", 1)[0],
                hand_id=hand_id,
                hand_number=int(row.get("hand_number", 0) or 0),
                move_type=str(decision.get("move_type", "")),
                amount=int(decision.get("amount", 0) or 0),
                reason=str(data.get("reason", "")),
                scores=scores,
                features=features,
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


def collect_minimax_turn_transcripts(
    minimax_decisions: list[MiniMaxDecisionRecord],
) -> list[MiniMaxTurnTranscript]:
    transcripts: list[MiniMaxTurnTranscript] = []
    for decision in sorted(minimax_decisions, key=lambda item: (item.timestamp, item.player_name, item.hand_id)):
        prompt_text, output_text = read_transcript_sections(decision.transcript_path)
        transcripts.append(
            MiniMaxTurnTranscript(
                timestamp=decision.timestamp,
                hand_id=decision.hand_id,
                hand_number=decision.hand_number,
                player_id=decision.player_id,
                player_name=decision.player_name,
                move_type=decision.move_type,
                amount=decision.amount,
                source=decision.source,
                reason=decision.reason,
                transcript_path=decision.transcript_path,
                prompt_text=prompt_text,
                output_text=output_text,
                raw_response=decision.raw_response,
            )
        )
    return transcripts


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
    guarded_decisions: list[GuardedDecisionRecord],
    minimax_decisions: list[MiniMaxDecisionRecord],
    transcript_limit: int,
) -> str:
    lines = [f"Remote bot match over {len(hands)} hands", ""]
    totals = Counter[str]()
    wins = Counter[str]()
    action_totals: dict[str, Counter[str]] = defaultdict(Counter)

    for hand in hands:
        winners = [player.name for player in players if player.seat_index in hand.winner_seats]
        winner_names = ", ".join(winners)
        lines.append(f"Hand {hand.hand_number} | {hand.hand_id}")
        lines.append(f"  winners={winner_names or '-'}")
        deltas = []
        for player in players:
            delta = hand.chip_deltas.get(player.seat_index, 0)
            totals[player.name] += delta
            if player.seat_index in hand.winner_seats:
                wins[player.name] += 1
            deltas.append(f"{player.name}:{delta:+d}")
            action_totals[player.name].update(hand.action_counts.get(player.player_id, Counter()))
        lines.append(f"  chip_deltas={' '.join(deltas)}")
        lines.append("")

    for player in players:
        rates = action_rates(action_totals[player.name])
        lines.append(f"{player.name} | seat={player.seat_index + 1}")
        lines.append(f"  chip_delta={totals[player.name]:+d} wins={wins[player.name]}")
        lines.append(
            "  actions="
            f"fold:{action_totals[player.name].get('FOLD', 0)} "
            f"check:{action_totals[player.name].get('CHECK', 0)} "
            f"call:{action_totals[player.name].get('CALL', 0)} "
            f"raise:{action_totals[player.name].get('RAISE', 0)} "
            f"all_in:{action_totals[player.name].get('ALL_IN', 0)}"
        )
        lines.append(
            "  rates="
            f"fold:{rates['fold_rate']:.3f} check:{rates['check_rate']:.3f} call:{rates['call_rate']:.3f} "
            f"raise:{rates['raise_rate']:.3f} all_in:{rates['all_in_rate']:.3f}"
        )
        lines.append("")

    source_counts = Counter(decision.source for decision in minimax_decisions)
    minimax_action_counts = Counter(decision.move_type for decision in minimax_decisions)
    non_check_actions = minimax_action_counts.get("FOLD", 0) + minimax_action_counts.get("RAISE", 0) + minimax_action_counts.get("CALL", 0) + minimax_action_counts.get("ALL_IN", 0)
    lines.append("MiniMax action focus")
    lines.append(
        "  "
        f"check={minimax_action_counts.get('CHECK', 0)} "
        f"call={minimax_action_counts.get('CALL', 0)} "
        f"raise={minimax_action_counts.get('RAISE', 0)} "
        f"fold={minimax_action_counts.get('FOLD', 0)} "
        f"all_in={minimax_action_counts.get('ALL_IN', 0)} "
        f"non_check={non_check_actions}"
    )
    lines.append("")
    lines.append("All bot decisions")
    for decision in guarded_decisions:
        suffix = f" amount={decision.amount}" if decision.amount else ""
        lines.append(f"  Guarded | {decision.player_name} | {decision.hand_id} | {decision.move_type}{suffix}")
        if decision.reason:
            lines.append(f"    reason={decision.reason}")
    for decision in minimax_decisions:
        suffix = f" amount={decision.amount}" if decision.amount else ""
        lines.append(f"  LLM | {decision.player_name} | {decision.hand_id} | {decision.source} | {decision.move_type}{suffix}")
        if decision.reason:
            lines.append(f"    reason={decision.reason}")
        if decision.raw_response:
            lines.append(f"    raw={decision.raw_response[:180].replace(chr(10), ' ')}")

    lines.append("MiniMax decisions")
    lines.append(
        f"  total={len(minimax_decisions)} model={source_counts.get('model', 0)} fallback={source_counts.get('fallback', 0)}"
    )
    minimax_subset = minimax_decisions if transcript_limit <= 0 else minimax_decisions[-transcript_limit:]
    for decision in minimax_subset:
        suffix = f" amount={decision.amount}" if decision.amount else ""
        lines.append(
            f"  {decision.hand_id} | {decision.source} | {decision.move_type}{suffix} | {decision.transcript_path}"
        )
        if decision.reason:
            lines.append(f"    reason={decision.reason}")
    return "\n".join(lines)


def render_transcript_timeline(turns: list[MiniMaxTurnTranscript]) -> str:
    lines = ["MiniMax turn timeline", ""]
    for index, turn in enumerate(turns, start=1):
        suffix = f" amount={turn.amount}" if turn.amount else ""
        lines.append(
            f"Turn {index} | {turn.timestamp} | hand={turn.hand_number} | {turn.player_name} | result={turn.move_type}{suffix} | source={turn.source}"
        )
        if turn.reason:
            lines.append(f"  reason={turn.reason}")
        if turn.transcript_path:
            lines.append(f"  transcript={turn.transcript_path}")
        lines.append("  prompt:")
        if turn.prompt_text:
            for line in turn.prompt_text.splitlines():
                lines.append(f"    {line}")
        else:
            lines.append("    <missing prompt>")
        lines.append("  output:")
        if turn.output_text:
            for line in turn.output_text.splitlines():
                lines.append(f"    {line}")
        elif turn.raw_response:
            for line in turn.raw_response.splitlines():
                lines.append(f"    {line}")
        else:
            lines.append("    <missing output>")
        lines.append("")
    return "\n".join(lines).rstrip()


def main() -> int:
    args = parse_args()
    session = RemoteMatchSession(args.address, poll_interval=args.poll_interval)
    session.login(args.owner_name)

    if args.guarded_bots < 0 or args.minimax_bots < 0:
        raise SystemExit("Bot counts must be >= 0.")
    if args.guarded_bots + args.minimax_bots < 2:
        raise SystemExit("At least two bots are required to start a hand.")
    if args.guarded_bots + args.minimax_bots > 6:
        raise SystemExit("The table only has 6 seats.")

    hand_results: list[poker_pb2.HandResult] = []
    session.create_room(args.room_name)
    for _ in range(args.guarded_bots):
        session.add_guarded_bot()
    for _ in range(args.minimax_bots):
        session.add_minimax_bot()
    players = session.wait_for_bot_counts(guarded_count=args.guarded_bots, minimax_count=args.minimax_bots)

    for _ in range(args.hands):
        hand_result = session.run_hand(args.timeout)
        hand_results.append(hand_result)
        session.wait_for(
            lambda: session.snapshot is not None and session.snapshot.room_status == poker_pb2.OPEN,
            timeout=15.0,
            description="room to reopen after the hand",
        )
        if any(delta.final_stack <= 0 for delta in hand_result.chip_deltas):
            break

    hand_records: list[HandMatchRecord] = []
    all_guarded_decisions: list[GuardedDecisionRecord] = []
    all_minimax_decisions: list[MiniMaxDecisionRecord] = []
    players_by_seat = {player.seat_index: player for player in players}
    room_id = session.room_id
    store = GameLogStore(Path(args.logs_root), "server", room_id)
    hand_ids = [result.hand_id for result in hand_results]
    all_guarded_decisions.extend(collect_guarded_decisions(store, room_id, hand_ids))
    all_minimax_decisions.extend(collect_minimax_decisions(store, room_id, hand_ids))
    for result in hand_results:
        action_counts = collect_hand_action_counts(store, room_id, [result.hand_id])
        hand_records.append(build_hand_record(result, action_counts, players_by_seat))

    print(render_summary(hand_records, players, all_guarded_decisions, all_minimax_decisions, args.transcript_limit))
    print()
    print(render_transcript_timeline(collect_minimax_turn_transcripts(all_minimax_decisions)))

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
            "guarded_decisions": [decision.__dict__ for decision in all_guarded_decisions],
            "minimax_decisions": [decision.__dict__ for decision in all_minimax_decisions],
            "minimax_turns": [turn.__dict__ for turn in collect_minimax_turn_transcripts(all_minimax_decisions)],
        }
        print()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    session.leave_room()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
