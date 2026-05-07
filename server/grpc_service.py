from __future__ import annotations

from collections import defaultdict
from concurrent import futures
from queue import Queue
import threading
import uuid

import grpc

from proto_gen import poker_pb2, poker_pb2_grpc
from server.room import PokerRoom
from shared.cards import Card


class PokerService(poker_pb2_grpc.PokerServiceServicer):
    def __init__(self) -> None:
        self.rooms: dict[str, PokerRoom] = {}
        self.subscribers: dict[str, list[tuple[str, Queue[poker_pb2.ServerEvent]]]] = defaultdict(list)
        self.lock = threading.RLock()

    def Play(self, request_iterator, context):
        player_id = uuid.uuid4().hex
        room_id = ""
        outgoing: Queue[poker_pb2.ServerEvent] = Queue()

        def consume_requests() -> None:
            nonlocal room_id
            try:
                for event in request_iterator:
                    try:
                        with self.lock:
                            payload = event.WhichOneof("payload")
                            if payload == "join_room":
                                room_id = event.join_room.room_id.strip() or "lobby"
                                room = self.get_room(room_id)
                                room.join(player_id, event.join_room.name)
                                self.subscribers[room_id].append((player_id, outgoing))
                                outgoing.put(poker_pb2.ServerEvent(joined=poker_pb2.Joined(player_id=player_id, room_id=room_id)))
                                self.broadcast(room_id)
                            elif not room_id:
                                raise ValueError("Join a room first")
                            else:
                                self.handle_room_event(player_id, room_id, event)
                                self.broadcast(room_id)
                    except Exception as exc:
                        outgoing.put(poker_pb2.ServerEvent(error=poker_pb2.Error(message=str(exc))))
            finally:
                with self.lock:
                    if room_id:
                        room = self.rooms.get(room_id)
                        if room:
                            room.leave(player_id)
                            self.broadcast(room_id)
                        self.subscribers[room_id] = [
                            subscriber for subscriber in self.subscribers[room_id] if subscriber[1] is not outgoing
                        ]

        threading.Thread(target=consume_requests, daemon=True).start()

        while context.is_active():
            yield outgoing.get()

    def get_room(self, room_id: str) -> PokerRoom:
        if room_id not in self.rooms:
            self.rooms[room_id] = PokerRoom(room_id)
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

    def broadcast(self, room_id: str) -> None:
        for player_id, subscriber in list(self.subscribers[room_id]):
            subscriber.put(self.snapshot_event(room_id, player_id))

    def snapshot_event(self, room_id: str, hero_player_id: str) -> poker_pb2.ServerEvent:
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
            )
            for seat in room.seats
        )
        snapshot.board.extend(card_to_proto(card) for card in room.board)
        snapshot.hero_cards.extend(card_to_proto(card) for card in room.hero_cards(hero_player_id))
        return poker_pb2.ServerEvent(snapshot=snapshot)


def card_to_proto(card: Card):
    return poker_pb2.Card(suit=getattr(poker_pb2, card.suit), rank=getattr(poker_pb2, card.rank))


def create_server() -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    poker_pb2_grpc.add_PokerServiceServicer_to_server(PokerService(), server)
    server.add_insecure_port("[::]:50051")
    return server
