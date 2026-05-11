import random
import unittest
from tempfile import TemporaryDirectory

from src.server.room import PokerRoom
from src.shared.game_logging import GameLogStore
from src.shared.hand_replay import load_hand_replay, render_hand_replay


class HandReplayTest(unittest.TestCase):
    def test_render_hand_replay_from_logged_hand(self) -> None:
        with TemporaryDirectory() as temp_dir:
            logger = GameLogStore(temp_dir, "server", "rooms")
            room = PokerRoom("test-room", logger=logger.with_owner("test-room"), rng=random.Random(0))
            room.join("p1", "Alice")
            room.join("p2", "Bot")
            room.sit("p1", 0)
            room.sit("p2", 1)
            room.set_ready("p1", True)
            room.set_ready("p2", True)
            room.start_hand()
            room.player_move(room.seats[room.active_seat].player_id, "FOLD")

            hand_id = room.last_hand_summary.hand_id
            replay = load_hand_replay(logger.with_owner("test-room"), room_id="test-room", hand_id=hand_id)
            rendered = render_hand_replay(replay)

            self.assertIn("Hand 1 replay", rendered)
            self.assertIn(hand_id, rendered)
            self.assertIn("HAND_START", rendered)
            self.assertIn("ACTION", rendered)
            self.assertIn("HAND_END", rendered)


if __name__ == "__main__":
    unittest.main()
