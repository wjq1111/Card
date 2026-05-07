from __future__ import annotations

from queue import Queue
import threading

import grpc

from proto_gen import poker_pb2, poker_pb2_grpc


class PokerClientConnection:
    def __init__(self, address: str) -> None:
        self.address = address
        self.outgoing: Queue[poker_pb2.ClientEvent] = Queue()
        self.incoming: Queue[poker_pb2.ServerEvent] = Queue()
        self.channel = grpc.insecure_channel(address)
        self.stub = poker_pb2_grpc.PokerServiceStub(self.channel)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def send(self, event: poker_pb2.ClientEvent) -> None:
        self.outgoing.put(event)

    def poll(self) -> list[poker_pb2.ServerEvent]:
        events: list[poker_pb2.ServerEvent] = []
        while not self.incoming.empty():
            events.append(self.incoming.get())
        return events

    def _run(self) -> None:
        try:
            for event in self.stub.Play(self._events()):
                self.incoming.put(event)
        except grpc.RpcError as exc:
            self.incoming.put(poker_pb2.ServerEvent(error=poker_pb2.Error(message=exc.details() or str(exc))))

    def _events(self):
        while True:
            yield self.outgoing.get()
