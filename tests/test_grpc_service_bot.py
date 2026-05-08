import random
import unittest
from queue import Queue
from unittest.mock import patch

from src.proto_gen import poker_pb2
from src.server.grpc_service import BOT_PREFIX, PokerService
from src.server.room import Phase


class PokerServiceBotTest(unittest.TestCase):
    def build_service(self) -> PokerService:
        with patch("src.server.grpc_service.threading.Thread.start", return_value=None):
            return PokerService()

    def test_add_guarded_bot_seats_and_readies_bot(self) -> None:
        service = self.build_service()
        service.player_names["owner"] = "Owner"
        service.player_avatars["owner"] = "mint"
        service.player_chip_balances["owner"] = 2000
        service.player_locations["owner"] = ""

        room_id = service.create_room_for_player("owner", "Bot Room")
        service.join_player_to_room("owner", room_id, Queue())
        room = service.rooms[room_id]
        room.sit("owner", 0)

        service.add_guarded_bot("owner", room)

        bot_ids = [player_id for player_id in room.players if player_id.startswith(BOT_PREFIX)]
        self.assertEqual(len(bot_ids), 1)
        bot_seat = room.find_seat(bot_ids[0])
        self.assertIsNotNone(bot_seat)
        self.assertTrue(bot_seat.ready)
        self.assertTrue(bot_seat.name.startswith("Guard Bot"))

    def test_run_service_bots_plays_when_bot_turns_arrive(self) -> None:
        service = self.build_service()
        room = service.create_room_for_test()
        service.add_guarded_bot("owner", room)
        room.set_ready("owner", True)
        room.start_hand()
        bot_ids = [player_id for player_id in room.players if player_id.startswith(BOT_PREFIX)]
        bot_id = bot_ids[0]
        room.active_seat = room.require_seat(bot_id).seat_index

        changed = service.run_service_bots(room)

        self.assertTrue(changed)
        self.assertNotEqual(room.active_seat, room.require_seat(bot_id).seat_index)
        self.assertTrue(any("bot chose" in line for line in room.log))

    def test_room_with_only_bots_is_removed_when_last_human_leaves(self) -> None:
        service = self.build_service()
        room = service.create_room_for_test()
        service.add_guarded_bot("owner", room)

        service.remove_player_from_room("owner", room.room_id)

        self.assertNotIn(room.room_id, service.rooms)


def _create_room_for_test(self: PokerService):
    self.player_names["owner"] = "Owner"
    self.player_avatars["owner"] = "mint"
    self.player_chip_balances["owner"] = 2000
    self.player_locations["owner"] = ""
    room_id = self.create_room_for_player("owner", "Bot Room")
    self.join_player_to_room("owner", room_id, Queue())
    room = self.rooms[room_id]
    room.sit("owner", 0)
    room.phase = Phase.WAITING
    return room


PokerService.create_room_for_test = _create_room_for_test


if __name__ == "__main__":
    unittest.main()
