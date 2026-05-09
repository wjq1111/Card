from __future__ import annotations

from collections import defaultdict
from concurrent import futures
from queue import Queue
import random
import threading
import time
import uuid

import grpc

from src.proto_gen import poker_pb2, poker_pb2_grpc
from src.server.bots.controller import play_bot_turn
from src.server.bots.models import BotProfile, ScoreWeights
from src.server.chip_store import PlayerChipStore
from src.server.room import PokerRoom, RoomStatus, STARTING_CHIPS
from src.shared.cards import Card
from src.shared.game_logging import GameLogStore


BOT_PREFIX = "bot:"
BOT_AVATAR_ID = "violet"
DEFAULT_BOT_PROFILE = BotProfile(
    name="guarded",
    looseness=0.55,
    aggression=0.52,
    bluff_rate=0.09,
    risk_tolerance=0.49,
    randomness=0.0,
)
DEFAULT_BOT_WEIGHTS = ScoreWeights(
    name="guarded",
    call_opponent_aggression=0.24,
    fold_recent_raise_pressure=0.16,
    raise_opponent_fold_to_raise=0.24,
    raise_opponent_vpip=-0.20,
)


class PokerService(poker_pb2_grpc.PokerServiceServicer):
    def __init__(self) -> None:
        self.rooms: dict[str, PokerRoom] = {}
        self.room_subscribers: dict[str, list[tuple[str, Queue[poker_pb2.ServerEvent]]]] = defaultdict(list)
        self.lobby_subscribers: dict[str, Queue[poker_pb2.ServerEvent]] = {}
        self.reconnect_tokens: dict[str, str] = {}
        self.player_names: dict[str, str] = {}
        self.player_avatars: dict[str, str] = {}
        self.player_locations: dict[str, str] = {}
        self.player_chip_balances: dict[str, int] = {}
        self.bot_profiles: dict[str, BotProfile] = {}
        self.bot_weights: dict[str, ScoreWeights] = {}
        self.bot_rngs: dict[str, random.Random] = {}
        self.bot_action_deadlines: dict[str, tuple[tuple[object, ...], float]] = {}
        self.lock = threading.RLock()
        self.server_logs = GameLogStore("runtime_logs", "server", "rooms")
        self.chip_store = PlayerChipStore("runtime_logs/player_chips.json")
        self._ticker = threading.Thread(target=self._room_loop, daemon=True)
        self._ticker.start()

    def Play(self, request_iterator, context):
        player_id = uuid.uuid4().hex
        reconnect_token = uuid.uuid4().hex
        outgoing: Queue[poker_pb2.ServerEvent] = Queue()

        def consume_requests() -> None:
            nonlocal player_id, reconnect_token
            try:
                for event in request_iterator:
                    try:
                        with self.lock:
                            payload = event.WhichOneof("payload")
                            if payload == "login":
                                player_id, reconnect_token = self.handle_login(event, outgoing, player_id, reconnect_token)
                            elif payload == "reconnect":
                                player_id, reconnect_token = self.handle_reconnect(event, outgoing)
                            elif payload == "heartbeat":
                                outgoing.put(
                                    self.server_event(
                                        request_id=event.request_id,
                                        server_notice=poker_pb2.ServerNotice(message="heartbeat_ack"),
                                    )
                                )
                            elif not self.is_logged_in(player_id):
                                raise ValueError("Login first")
                            elif payload == "list_rooms":
                                outgoing.put(self.lobby_snapshot_event(player_id, request_id=event.request_id))
                            elif payload == "create_room":
                                room_id = self.create_room_for_player(player_id, event.create_room.display_name)
                                self.join_player_to_room(player_id, room_id, outgoing)
                                outgoing.put(self.server_event(request_id=event.request_id, joined=self.joined_payload(player_id, room_id)))
                            elif payload == "join_room_by_id":
                                room_id = event.join_room_by_id.room_id.strip()
                                if not room_id:
                                    raise ValueError("Room id is required")
                                self.join_player_to_room(player_id, room_id, outgoing)
                                outgoing.put(self.server_event(request_id=event.request_id, joined=self.joined_payload(player_id, room_id)))
                            elif payload == "leave_room":
                                self.leave_current_room(player_id, outgoing)
                                outgoing.put(self.lobby_snapshot_event(player_id, request_id=event.request_id))
                            elif payload in {"sit_down", "stand_up", "change_seat", "set_ready", "start_hand", "player_move", "chat_message"}:
                                room_id = self.require_room_location(player_id)
                                self.handle_room_event(player_id, room_id, event)
                                self.broadcast_room(room_id)
                                self.broadcast_lobby()
                            else:
                                raise ValueError("Unsupported request")
                    except Exception as exc:
                        outgoing.put(
                            self.server_event(
                                request_id=getattr(event, "request_id", ""),
                                error=poker_pb2.Error(code="INVALID_ACTION", message=str(exc)),
                            )
                        )
            finally:
                with self.lock:
                    self.disconnect_player(player_id, outgoing)

        threading.Thread(target=consume_requests, daemon=True).start()

        while context.is_active():
            yield outgoing.get()

    def handle_login(
        self,
        event: poker_pb2.ClientEvent,
        outgoing: Queue[poker_pb2.ServerEvent],
        player_id: str,
        reconnect_token: str,
    ) -> tuple[str, str]:
        if event.player_id and self.reconnect_tokens.get(event.player_id) == event.reconnect_token:
            player_id = event.player_id
            reconnect_token = event.reconnect_token
        name = event.login.name.strip()
        if not name:
            raise ValueError("Player name is required")
        avatar_id = event.login.avatar_id.strip()
        chips = self.chip_store.get_or_create(name)
        self.player_names[player_id] = name
        self.player_avatars[player_id] = avatar_id
        self.player_chip_balances[player_id] = chips
        self.reconnect_tokens[player_id] = reconnect_token
        self.player_locations[player_id] = ""
        self.lobby_subscribers[player_id] = outgoing
        outgoing.put(
            self.server_event(
                request_id=event.request_id,
                login_accepted=poker_pb2.LoginAccepted(
                    player_id=player_id,
                    player_name=name,
                    reconnect_token=reconnect_token,
                    avatar_id=avatar_id,
                ),
            )
        )
        outgoing.put(self.lobby_snapshot_event(player_id, request_id=event.request_id))
        return player_id, reconnect_token

    def handle_reconnect(
        self,
        event: poker_pb2.ClientEvent,
        outgoing: Queue[poker_pb2.ServerEvent],
    ) -> tuple[str, str]:
        requested_player_id = event.reconnect.player_id or event.player_id
        token = event.reconnect.reconnect_token or event.reconnect_token
        if not requested_player_id or self.reconnect_tokens.get(requested_player_id) != token:
            raise ValueError("Reconnect token is invalid")
        self.lobby_subscribers[requested_player_id] = outgoing
        location = self.player_locations.get(requested_player_id, "")
        if location:
            self.attach_room_subscriber(location, requested_player_id, outgoing)
            outgoing.put(self.snapshot_event(location, requested_player_id, request_id=event.request_id))
        else:
            outgoing.put(self.lobby_snapshot_event(requested_player_id, request_id=event.request_id))
        return requested_player_id, token

    def is_logged_in(self, player_id: str) -> bool:
        return player_id in self.player_names

    def create_room_for_player(self, player_id: str, display_name: str) -> str:
        room_id = self.generate_room_id()
        room = PokerRoom(
            room_id,
            display_name=display_name.strip() or room_id,
            logger=self.server_logs.with_owner(room_id),
            chip_resolver=self.resolve_player_chips,
            chip_persistor=self.persist_player_chips,
        )
        self.rooms[room_id] = room
        self.broadcast_lobby()
        return room_id

    def generate_room_id(self) -> str:
        while True:
            room_id = f"room-{uuid.uuid4().hex[:6]}"
            if room_id not in self.rooms:
                return room_id

    def join_player_to_room(self, player_id: str, room_id: str, outgoing: Queue[poker_pb2.ServerEvent]) -> None:
        if room_id not in self.rooms:
            raise ValueError("Room does not exist")
        current_room_id = self.player_locations.get(player_id, "")
        if current_room_id == room_id:
            return
        if current_room_id:
            self.remove_player_from_room(player_id, current_room_id)
        room = self.rooms[room_id]
        room.join(player_id, self.player_names[player_id], self.player_avatars.get(player_id, ""))
        self.player_locations[player_id] = room_id
        self.attach_room_subscriber(room_id, player_id, outgoing)
        self.lobby_subscribers[player_id] = outgoing
        self.broadcast_room(room_id)
        self.broadcast_lobby()

    def leave_current_room(self, player_id: str, outgoing: Queue[poker_pb2.ServerEvent]) -> None:
        room_id = self.player_locations.get(player_id, "")
        if not room_id:
            return
        self.remove_player_from_room(player_id, room_id)
        self.player_locations[player_id] = ""
        self.lobby_subscribers[player_id] = outgoing
        self.broadcast_lobby()

    def remove_player_from_room(self, player_id: str, room_id: str) -> None:
        room = self.rooms.get(room_id)
        if not room:
            return
        room.leave(player_id)
        if self.is_bot_player(player_id):
            self.cleanup_bot(player_id)
        self.room_subscribers[room_id] = [entry for entry in self.room_subscribers[room_id] if entry[0] != player_id]
        if not self.human_players_in_room(room):
            self.cleanup_room_bots(room)
            self.room_subscribers.pop(room_id, None)
            self.rooms.pop(room_id, None)
        elif room.is_empty():
            self.room_subscribers.pop(room_id, None)
            self.rooms.pop(room_id, None)
        else:
            self.promote_human_owner(room)
            self.broadcast_room(room_id)

    def attach_room_subscriber(self, room_id: str, player_id: str, outgoing: Queue[poker_pb2.ServerEvent]) -> None:
        self.room_subscribers[room_id] = [entry for entry in self.room_subscribers[room_id] if entry[0] != player_id]
        self.room_subscribers[room_id].append((player_id, outgoing))

    def disconnect_player(self, player_id: str, outgoing: Queue[poker_pb2.ServerEvent]) -> None:
        self.lobby_subscribers.pop(player_id, None)
        location = self.player_locations.get(player_id, "")
        if location:
            self.remove_player_from_room(player_id, location)
            self.player_locations[player_id] = ""
            self.broadcast_lobby()
        else:
            for room_id, subscribers in list(self.room_subscribers.items()):
                self.room_subscribers[room_id] = [entry for entry in subscribers if entry[1] is not outgoing]

    def require_room_location(self, player_id: str) -> str:
        room_id = self.player_locations.get(player_id, "")
        if not room_id:
            raise ValueError("Join a room first")
        return room_id

    def handle_room_event(self, player_id: str, room_id: str, event: poker_pb2.ClientEvent) -> None:
        room = self.rooms[room_id]
        payload = event.WhichOneof("payload")
        if payload == "sit_down":
            room.sit(player_id, event.sit_down.seat_index)
        elif payload == "stand_up":
            room.stand(player_id)
        elif payload == "change_seat":
            room.change_seat(player_id, event.change_seat.seat_index)
        elif payload == "set_ready":
            room.set_ready(player_id, event.set_ready.ready)
        elif payload == "start_hand":
            room.request_start(player_id)
        elif payload == "player_move":
            room.player_move(player_id, poker_pb2.MoveType.Name(event.player_move.type), event.player_move.amount)
        elif payload == "chat_message":
            message = event.chat_message.text.strip()
            if message == "/addbot":
                self.add_guarded_bot(player_id, room)
            elif message.startswith("/gm addchips "):
                self.grant_debug_chips(player_id, room, int(message.split()[-1]))
            else:
                room.log_line(f"{room.players.get(player_id, 'Player')}: {message[:120]}")

    def resolve_player_chips(self, player_id: str, player_name: str) -> int:
        return self.player_chip_balances.get(player_id, self.chip_store.get_or_create(player_name))

    def persist_player_chips(self, player_id: str, player_name: str, chips: int) -> None:
        stored = self.chip_store.set_chips(player_name, chips)
        self.player_chip_balances[player_id] = stored

    def grant_debug_chips(self, player_id: str, room: PokerRoom, amount: int) -> None:
        if amount <= 0:
            raise ValueError("GM 筹码数量必须大于 0")
        player_name = self.player_names.get(player_id, "Player")
        seat = room.find_seat(player_id)
        if seat:
            seat.chips += amount
            room.sync_player_chips(player_id, seat.chips)
            self.player_chip_balances[player_id] = seat.chips
            room.log_line(f"{seat.name} GM 增加了 {amount} 筹码", event_type="GM")
            return
        new_total = self.chip_store.add_chips(player_name, amount)
        self.player_chip_balances[player_id] = new_total
        room.log_line(f"{player_name} GM 增加了 {amount} 筹码（未入座）", event_type="GM")

    def _room_loop(self) -> None:
        while True:
            time.sleep(0.2)
            with self.lock:
                dirty_rooms: set[str] = set()
                now = time.monotonic()
                for room_id, room in list(self.rooms.items()):
                    if room.update(now):
                        dirty_rooms.add(room_id)
                    if self.run_service_bots(room, now):
                        dirty_rooms.add(room_id)
                for room_id in dirty_rooms:
                    self.broadcast_room(room_id)
                    self.broadcast_lobby()

    def broadcast_room(self, room_id: str) -> None:
        if room_id not in self.rooms:
            return
        for player_id, subscriber in list(self.room_subscribers[room_id]):
            subscriber.put(self.snapshot_event(room_id, player_id))

    def broadcast_lobby(self) -> None:
        for player_id, subscriber in list(self.lobby_subscribers.items()):
            if self.player_locations.get(player_id, ""):
                continue
            subscriber.put(self.lobby_snapshot_event(player_id))

    def lobby_snapshot_event(self, player_id: str, request_id: str = "") -> poker_pb2.ServerEvent:
        snapshot = poker_pb2.LobbySnapshot(
            hero_player_id=player_id,
            hero_name=self.player_names.get(player_id, ""),
            hero_avatar_id=self.player_avatars.get(player_id, ""),
        )
        for room in self.rooms.values():
            snapshot.rooms.append(
                poker_pb2.LobbyRoomInfo(
                    room_id=room.room_id,
                    display_name=room.display_name,
                    owner_player_id=room.owner_player_id,
                    owner_name=self.player_names.get(room.owner_player_id, room.players.get(room.owner_player_id, "")),
                    player_count=len(room.players),
                    seat_count=len(room.seats),
                    ready_count=room.ready_player_count(),
                    room_status=getattr(poker_pb2, room.room_status.value),
                )
            )
        return self.server_event(request_id=request_id, lobby_snapshot=snapshot)

    def snapshot_event(self, room_id: str, hero_player_id: str, request_id: str = "") -> poker_pb2.ServerEvent:
        room = self.rooms[room_id]
        snapshot = poker_pb2.RoomSnapshot(
            room_id=room.room_id,
            hero_player_id=hero_player_id,
            phase=getattr(poker_pb2, room.phase.value),
            pot=room.pot,
            current_bet=room.current_bet,
            min_raise=room.min_raise,
            dealer_seat=room.dealer_seat,
            active_seat=room.active_seat,
            hand_number=room.hand_number,
            log=room.log[-8:],
            current_hand_id=room.current_hand_id,
            starting_countdown_seconds=room.starting_countdown_seconds(time.monotonic()),
            owner_player_id=room.owner_player_id,
            room_status=getattr(poker_pb2, room.room_status.value),
        )
        snapshot.seats.extend(
            poker_pb2.Seat(
                seat_index=seat.seat_index,
                player_id=seat.player_id,
                name=seat.name,
                avatar_id=seat.avatar_id,
                chips=seat.chips,
                committed=seat.committed,
                folded=seat.folded,
                all_in=seat.all_in,
                ready=seat.ready,
                is_dealer=seat.seat_index == room.dealer_seat,
                is_turn=seat.seat_index == room.active_seat,
                hole_card_count=len(seat.hole_cards),
                hand_committed=seat.hand_committed,
                acted_this_round=seat.acted_this_round,
            )
            for seat in room.seats
        )
        snapshot.members.extend(
            poker_pb2.RoomMember(
                player_id=player_id,
                name=name,
                avatar_id=avatar_id,
                is_owner=is_owner,
                ready=ready,
                seat_index=seat_index,
            )
            for player_id, name, avatar_id, is_owner, seat_index, ready in room.members()
        )
        snapshot.board.extend(card_to_proto(card) for card in room.board)
        snapshot.hero_cards.extend(card_to_proto(card) for card in room.hero_cards(hero_player_id))
        if room.last_hand_summary:
            snapshot.last_hand_result.CopyFrom(hand_result_to_proto(room))
        return self.server_event(request_id=request_id, snapshot=snapshot)

    def joined_payload(self, player_id: str, room_id: str) -> poker_pb2.Joined:
        return poker_pb2.Joined(
            player_id=player_id,
            room_id=room_id,
            reconnect_token=self.reconnect_tokens[player_id],
        )

    def server_event(self, request_id: str = "", **payload) -> poker_pb2.ServerEvent:
        return poker_pb2.ServerEvent(event_id=uuid.uuid4().hex, request_id=request_id, **payload)

    def is_bot_player(self, player_id: str) -> bool:
        return player_id.startswith(BOT_PREFIX)

    def human_players_in_room(self, room: PokerRoom) -> list[str]:
        return [player_id for player_id in room.players if not self.is_bot_player(player_id)]

    def promote_human_owner(self, room: PokerRoom) -> None:
        if room.owner_player_id and not self.is_bot_player(room.owner_player_id):
            return
        humans = self.human_players_in_room(room)
        if humans:
            room.owner_player_id = humans[0]

    def cleanup_bot(self, bot_id: str) -> None:
        self.player_names.pop(bot_id, None)
        self.player_avatars.pop(bot_id, None)
        self.player_locations.pop(bot_id, None)
        self.player_chip_balances.pop(bot_id, None)
        self.bot_profiles.pop(bot_id, None)
        self.bot_weights.pop(bot_id, None)
        self.bot_rngs.pop(bot_id, None)
        self.bot_action_deadlines.pop(bot_id, None)

    def cleanup_room_bots(self, room: PokerRoom) -> None:
        for player_id in list(room.players):
            if self.is_bot_player(player_id):
                self.cleanup_bot(player_id)

    def add_guarded_bot(self, player_id: str, room: PokerRoom) -> None:
        if player_id != room.owner_player_id:
            raise ValueError("Only the room owner can add a bot")
        if room.room_status != RoomStatus.OPEN or room.phase.name != "WAITING":
            raise ValueError("Bots can only be added before a hand starts")
        open_seat = next((seat.seat_index for seat in room.seats if not seat.player_id), -1)
        if open_seat < 0:
            raise ValueError("No open seat is available for a bot")

        bot_number = sum(1 for member_id in room.players if self.is_bot_player(member_id)) + 1
        bot_id = f"{BOT_PREFIX}{uuid.uuid4().hex[:8]}"
        bot_name = f"Guard Bot {bot_number}"
        self.player_names[bot_id] = bot_name
        self.player_avatars[bot_id] = BOT_AVATAR_ID
        self.player_chip_balances[bot_id] = STARTING_CHIPS
        self.player_locations[bot_id] = room.room_id
        self.bot_profiles[bot_id] = DEFAULT_BOT_PROFILE.updated(name=bot_name)
        self.bot_weights[bot_id] = DEFAULT_BOT_WEIGHTS.updated(name=bot_name)
        self.bot_rngs[bot_id] = random.Random(hash((room.room_id, bot_id)) & 0xFFFFFFFF)

        room.join(bot_id, bot_name, BOT_AVATAR_ID)
        room.sit(bot_id, open_seat)
        room.set_ready(bot_id, True)
        room.log_line(f"{bot_name} joined as a guarded bot", event_type="BOT")

    def run_service_bots(self, room: PokerRoom, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        changed = False
        safety = 0
        while 0 <= room.active_seat < len(room.seats):
            seat = room.seats[room.active_seat]
            if not seat.player_id or not self.is_bot_player(seat.player_id):
                break
            turn_key = (
                room.room_id,
                room.current_hand_id,
                room.phase.value,
                room.active_seat,
                room.current_bet,
                seat.committed,
                seat.hand_committed,
                seat.chips,
            )
            tracked = self.bot_action_deadlines.get(seat.player_id)
            if tracked is None or tracked[0] != turn_key:
                self.bot_action_deadlines[seat.player_id] = (turn_key, now + 1.0)
                break
            if now < tracked[1]:
                break
            self.bot_action_deadlines.pop(seat.player_id, None)
            play_bot_turn(
                room,
                seat.player_id,
                profile=self.bot_profiles.get(seat.player_id, DEFAULT_BOT_PROFILE),
                weights=self.bot_weights.get(seat.player_id, DEFAULT_BOT_WEIGHTS),
                rng=self.bot_rngs.setdefault(seat.player_id, random.Random(0)),
            )
            changed = True
            safety += 1
            if safety >= 12:
                break
        return changed


def card_to_proto(card: Card):
    return poker_pb2.Card(suit=getattr(poker_pb2, card.suit), rank=getattr(poker_pb2, card.rank))


def hand_result_to_proto(room: PokerRoom):
    summary = room.last_hand_summary
    result = poker_pb2.HandResult(hand_id=summary.hand_id, hand_number=summary.hand_number)
    result.board.extend(card_to_proto(card) for card in summary.board)
    for award in summary.awards:
        result.pot_awards.append(
            poker_pb2.PotAward(
                amount=award.amount,
                winner_seats=award.winner_seats,
                eligible_seats=award.eligible_seats,
            )
        )
    result.winner_seats.extend(summary.winner_seats)
    for seat in room.seats:
        if seat.seat_index in summary.hand_names:
            result.shown_hands.append(
                poker_pb2.ShownHand(
                    seat_index=seat.seat_index,
                    cards=[card_to_proto(card) for card in seat.hole_cards],
                    hand_name=summary.hand_names[seat.seat_index],
                )
            )
    for seat_index, delta in summary.chip_deltas.items():
        result.chip_deltas.append(
            poker_pb2.ChipDelta(
                seat_index=seat_index,
                delta=delta,
                final_stack=summary.final_stacks.get(seat_index, 0),
            )
        )
    return result


def create_server() -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    poker_pb2_grpc.add_PokerServiceServicer_to_server(PokerService(), server)
    server.add_insecure_port("[::]:50051")
    return server
