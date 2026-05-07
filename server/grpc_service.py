from __future__ import annotations

from collections import defaultdict
from concurrent import futures
from queue import Queue
import threading
import time
import uuid

import grpc

from proto_gen import poker_pb2, poker_pb2_grpc
from server.room import PokerRoom
from shared.cards import Card
from shared.game_logging import GameLogStore


class PokerService(poker_pb2_grpc.PokerServiceServicer):
    def __init__(self) -> None:
        self.rooms: dict[str, PokerRoom] = {}
        self.subscribers: dict[str, list[tuple[str, Queue[poker_pb2.ServerEvent]]]] = defaultdict(list)
        self.reconnect_tokens: dict[str, str] = {}
        self.player_rooms: dict[str, str] = {}
        self.lock = threading.RLock()
        self.server_logs = GameLogStore("runtime_logs", "server", "rooms")
        self._ticker = threading.Thread(target=self._room_loop, daemon=True)
        self._ticker.start()

    def Play(self, request_iterator, context):
        player_id = uuid.uuid4().hex
        reconnect_token = uuid.uuid4().hex
        room_id = ""
        outgoing: Queue[poker_pb2.ServerEvent] = Queue()

        def consume_requests() -> None:
            nonlocal player_id, reconnect_token, room_id
            try:
                for event in request_iterator:
                    try:
                        with self.lock:
                            payload = event.WhichOneof("payload")
                            if payload == "join_room":
                                if event.player_id and self.reconnect_tokens.get(event.player_id) == event.reconnect_token:
                                    player_id = event.player_id
                                    reconnect_token = event.reconnect_token
                                room_id = event.join_room.room_id.strip() or "lobby"
                                room = self.get_room(room_id)
                                room.join(player_id, event.join_room.name)
                                self.reconnect_tokens[player_id] = reconnect_token
                                self.player_rooms[player_id] = room_id
                                self.subscribers[room_id].append((player_id, outgoing))
                                outgoing.put(
                                    self.server_event(
                                        request_id=event.request_id,
                                        joined=poker_pb2.Joined(
                                            player_id=player_id,
                                            room_id=room_id,
                                            reconnect_token=reconnect_token,
                                        ),
                                    )
                                )
                                self.broadcast(room_id)
                            elif payload == "reconnect":
                                player_id, room_id, reconnect_token = self.handle_reconnect(event, outgoing)
                                outgoing.put(self.snapshot_event(room_id, player_id, request_id=event.request_id))
                            elif payload == "heartbeat":
                                outgoing.put(
                                    self.server_event(
                                        request_id=event.request_id,
                                        server_notice=poker_pb2.ServerNotice(message="heartbeat_ack"),
                                    )
                                )
                            elif not room_id:
                                raise ValueError("Join a room first")
                            else:
                                self.handle_room_event(player_id, room_id, event)
                                self.broadcast(room_id)
                    except Exception as exc:
                        outgoing.put(
                            self.server_event(
                                request_id=getattr(event, "request_id", ""),
                                error=poker_pb2.Error(code="INVALID_ACTION", message=str(exc)),
                            )
                        )
            finally:
                with self.lock:
                    if room_id:
                        self.subscribers[room_id] = [
                            subscriber for subscriber in self.subscribers[room_id] if subscriber[1] is not outgoing
                        ]

        threading.Thread(target=consume_requests, daemon=True).start()

        while context.is_active():
            yield outgoing.get()

    def get_room(self, room_id: str) -> PokerRoom:
        if room_id not in self.rooms:
            self.rooms[room_id] = PokerRoom(room_id, logger=self.server_logs.with_owner(room_id))
        return self.rooms[room_id]

    def handle_room_event(self, player_id: str, room_id: str, event) -> None:
        room = self.get_room(room_id)
        payload = event.WhichOneof("payload")
        if payload == "sit_down":
            room.sit(player_id, event.sit_down.seat_index)
        elif payload == "stand_up":
            room.stand(player_id)
        elif payload == "set_ready":
            room.set_ready(player_id, event.set_ready.ready)
        elif payload == "start_hand":
            room.start_hand()
        elif payload == "player_move":
            room.player_move(player_id, poker_pb2.MoveType.Name(event.player_move.type), event.player_move.amount)
        elif payload == "chat_message":
            room.log_line(f"{room.players.get(player_id, 'Player')}: {event.chat_message.text[:120]}")

    def _room_loop(self) -> None:
        while True:
            time.sleep(0.2)
            with self.lock:
                dirty_rooms = [room_id for room_id, room in self.rooms.items() if room.update(time.monotonic())]
                for room_id in dirty_rooms:
                    self.broadcast(room_id)

    def handle_reconnect(self, event, outgoing) -> tuple[str, str, str]:
        requested_player_id = event.reconnect.player_id or event.player_id
        token = event.reconnect.reconnect_token or event.reconnect_token
        if not requested_player_id or self.reconnect_tokens.get(requested_player_id) != token:
            raise ValueError("Reconnect token is invalid")
        room_id = event.reconnect.room_id or self.player_rooms.get(requested_player_id, "")
        if not room_id:
            raise ValueError("No previous room can be restored")
        self.subscribers[room_id] = [
            subscriber for subscriber in self.subscribers[room_id] if subscriber[0] != requested_player_id
        ]
        self.subscribers[room_id].append((requested_player_id, outgoing))
        return requested_player_id, room_id, token

    def broadcast(self, room_id: str) -> None:
        for player_id, subscriber in list(self.subscribers[room_id]):
            subscriber.put(self.snapshot_event(room_id, player_id))

    def snapshot_event(self, room_id: str, hero_player_id: str, request_id: str = "") -> poker_pb2.ServerEvent:
        room = self.get_room(room_id)
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
            auto_start_countdown_seconds=room.countdown_seconds_remaining(time.monotonic()),
        )
        snapshot.seats.extend(
            poker_pb2.Seat(
                seat_index=seat.seat_index,
                player_id=seat.player_id,
                name=seat.name,
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
        snapshot.board.extend(card_to_proto(card) for card in room.board)
        snapshot.hero_cards.extend(card_to_proto(card) for card in room.hero_cards(hero_player_id))
        if room.last_hand_summary:
            snapshot.last_hand_result.CopyFrom(hand_result_to_proto(room))
        return self.server_event(request_id=request_id, snapshot=snapshot)

    def server_event(self, request_id: str = "", **payload) -> poker_pb2.ServerEvent:
        return poker_pb2.ServerEvent(event_id=uuid.uuid4().hex, request_id=request_id, **payload)


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
