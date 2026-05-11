import random
import unittest

from src.server.bots.controller import build_observation, play_bot_turn
from src.server.bots.models import BotObservation, BotProfile, OpponentSnapshot, ScoreWeights
from src.server.bots.features import extract_features
from src.server.bots.policy import decide_action, legal_candidates
from src.server.room import Phase, PokerRoom
from src.shared.cards import Card


def c(rank: str, suit: str = "SPADES") -> Card:
    return Card(suit=suit, rank=rank)


PROFILE = BotProfile(randomness=0.0)


def obs(
    *,
    phase: str = "FLOP",
    hole_cards: tuple[Card, ...] = (c("ACE"), c("KING", "HEARTS")),
    board_cards: tuple[Card, ...] = (c("TWO", "CLUBS"), c("SEVEN", "DIAMONDS"), c("QUEEN", "SPADES")),
    pot: int = 100,
    current_bet: int = 0,
    min_raise: int = 20,
    committed: int = 0,
    chips: int = 1000,
    legal_actions: tuple[str, ...] = ("CHECK", "RAISE", "ALL_IN"),
    opponents: tuple[OpponentSnapshot, ...] = (),
) -> BotObservation:
    return BotObservation(
        player_id="bot",
        seat_index=0,
        seat_count=2,
        phase=phase,
        hole_cards=hole_cards,
        board_cards=board_cards,
        pot=pot,
        current_bet=current_bet,
        min_raise=min_raise,
        committed=committed,
        chips=chips,
        hand_committed=committed,
        dealer_seat=0,
        active_seat=0,
        live_player_count=2,
        acting_player_count=2,
        legal_actions=legal_actions,
        opponents=opponents,
    )


class BotPolicyTest(unittest.TestCase):
    def test_check_when_no_bet_and_weak_hand(self) -> None:
        decision = decide_action(
            obs(
                hole_cards=(c("THREE"), c("EIGHT", "HEARTS")),
                board_cards=(c("ACE", "CLUBS"), c("KING", "DIAMONDS"), c("QUEEN", "SPADES")),
                legal_actions=("CHECK",),
            ),
            profile=PROFILE,
            rng=random.Random(0),
        )

        self.assertEqual(decision.move_type, "CHECK")

    def test_fold_weak_hand_facing_large_bet(self) -> None:
        decision = decide_action(
            obs(
                hole_cards=(c("THREE"), c("EIGHT", "HEARTS")),
                board_cards=(c("ACE", "CLUBS"), c("KING", "DIAMONDS"), c("QUEEN", "SPADES")),
                pot=100,
                current_bet=700,
                legal_actions=("FOLD", "CALL", "ALL_IN"),
            ),
            profile=PROFILE,
            rng=random.Random(0),
        )

        self.assertEqual(decision.move_type, "FOLD")

    def test_call_draw_with_good_pot_odds(self) -> None:
        decision = decide_action(
            obs(
                hole_cards=(c("ACE", "HEARTS"), c("KING", "HEARTS")),
                board_cards=(c("TWO", "HEARTS"), c("SEVEN", "HEARTS"), c("QUEEN", "SPADES")),
                pot=200,
                current_bet=20,
                legal_actions=("FOLD", "CALL", "RAISE", "ALL_IN"),
            ),
            profile=PROFILE,
            rng=random.Random(0),
        )

        self.assertEqual(decision.move_type, "CALL")

    def test_raise_strong_made_hand(self) -> None:
        decision = decide_action(
            obs(
                hole_cards=(c("ACE", "HEARTS"), c("ACE", "SPADES")),
                board_cards=(c("ACE", "CLUBS"), c("SEVEN", "DIAMONDS"), c("TWO", "SPADES")),
                pot=100,
                legal_actions=("CHECK", "RAISE", "ALL_IN"),
            ),
            profile=PROFILE,
            rng=random.Random(0),
        )

        self.assertEqual(decision.move_type, "RAISE")
        self.assertGreaterEqual(decision.amount, 20)

    def test_all_in_is_penalized_for_weak_hand(self) -> None:
        decision = decide_action(
            obs(
                hole_cards=(c("THREE"), c("EIGHT", "HEARTS")),
                board_cards=(c("ACE", "CLUBS"), c("KING", "DIAMONDS"), c("QUEEN", "SPADES")),
                pot=100,
                current_bet=700,
                legal_actions=("FOLD", "CALL", "ALL_IN"),
            ),
            profile=PROFILE,
            rng=random.Random(0),
        )

        self.assertNotEqual(decision.move_type, "ALL_IN")

    def test_raise_amount_is_within_room_limits(self) -> None:
        observation = obs(
            pot=100,
            current_bet=40,
            min_raise=20,
            committed=10,
            chips=200,
            legal_actions=("FOLD", "CALL", "RAISE", "ALL_IN"),
        )
        raises = [candidate for candidate in legal_candidates(observation) if candidate.move_type == "RAISE"]

        self.assertTrue(raises)
        for candidate in raises:
            self.assertGreaterEqual(candidate.amount, observation.minimum_raise_to)
            self.assertLess(candidate.amount, observation.maximum_raise_to)

    def test_raise_candidates_are_rounded_to_human_like_bet_sizes(self) -> None:
        observation = obs(
            pot=295,
            current_bet=50,
            min_raise=50,
            committed=0,
            chips=1000,
            legal_actions=("FOLD", "CALL", "RAISE", "ALL_IN"),
        )

        raises = [candidate.amount for candidate in legal_candidates(observation) if candidate.move_type == "RAISE"]

        self.assertTrue(raises)
        self.assertTrue(all(amount % 10 == 0 for amount in raises))
        self.assertNotIn(147, raises)

    def test_custom_weights_can_flip_decision(self) -> None:
        observation = obs(
            hole_cards=(c("ACE", "HEARTS"), c("KING", "HEARTS")),
            board_cards=(c("TWO", "HEARTS"), c("SEVEN", "HEARTS"), c("QUEEN", "SPADES")),
            pot=200,
            current_bet=20,
            legal_actions=("FOLD", "CALL", "RAISE", "ALL_IN"),
        )
        aggressive_weights = ScoreWeights(name="aggressive")
        folding_weights = ScoreWeights(
            name="foldy",
            call_pot_odds_fit=0.05,
            call_draw_strength=0.05,
            call_equity=-0.20,
            fold_pressure_score=0.80,
            fold_equity=0.70,
            fold_pot_odds_fit=-0.05,
            raise_value_made_strength=0.05,
            raise_bluff_draw_strength=0.05,
            raise_equity=0.0,
            raise_aggression=0.0,
            raise_opponent_fold_to_raise=0.0,
            all_in_weak_penalty=-1.0,
            all_in_equity=0.0,
        )

        default_decision = decide_action(observation, profile=PROFILE, weights=aggressive_weights, rng=random.Random(0))
        flipped_decision = decide_action(observation, profile=PROFILE, weights=folding_weights, rng=random.Random(0))

        self.assertEqual(default_decision.move_type, "CALL")
        self.assertEqual(flipped_decision.move_type, "FOLD")

    def test_aggressive_opponent_profile_can_push_call_over_fold(self) -> None:
        opponent = OpponentSnapshot(
            player_id="villain",
            seat_index=1,
            chips=1000,
            committed=700,
            hand_committed=700,
            folded=False,
            all_in=False,
            acted_this_round=True,
            last_action="RAISE",
            last_action_phase="TURN",
            vpip_rate=0.55,
            pfr_rate=0.40,
            aggression_factor=4.0,
            fold_to_raise_rate=0.20,
            recent_raise_rate=0.75,
        )
        folding_weights = ScoreWeights(
            call_made_strength=0.10,
            call_draw_strength=0.05,
            call_equity=-0.10,
            call_pot_odds_fit=0.10,
            call_opponent_aggression=0.0,
            fold_pressure_score=0.65,
            fold_equity=0.70,
            fold_recent_raise_pressure=0.45,
        )
        hero_calling_weights = folding_weights.updated(
            call_equity=0.25,
            call_opponent_aggression=0.80,
            fold_recent_raise_pressure=0.05,
        )
        observation = obs(
            hole_cards=(c("ACE", "SPADES"), c("QUEEN", "SPADES")),
            board_cards=(c("ACE", "CLUBS"), c("TEN", "HEARTS"), c("FOUR", "DIAMONDS"), c("TWO", "CLUBS")),
            pot=300,
            current_bet=120,
            committed=0,
            legal_actions=("FOLD", "CALL"),
            opponents=(opponent,),
        )

        fold_decision = decide_action(observation, profile=PROFILE, weights=folding_weights, rng=random.Random(0))
        call_decision = decide_action(observation, profile=PROFILE, weights=hero_calling_weights, rng=random.Random(0))

        self.assertEqual(fold_decision.move_type, "FOLD")
        self.assertEqual(call_decision.move_type, "CALL")

    def test_monte_carlo_equity_distinguishes_premium_from_trash_preflop(self) -> None:
        premium_features = extract_features(
            obs(phase="PREFLOP", hole_cards=(c("ACE", "HEARTS"), c("ACE", "SPADES")), board_cards=()),
            profile=PROFILE,
            rng=random.Random(0),
        )
        trash_features = extract_features(
            obs(phase="PREFLOP", hole_cards=(c("SEVEN", "CLUBS"), c("TWO", "DIAMONDS")), board_cards=()),
            profile=PROFILE,
            rng=random.Random(0),
        )

        self.assertGreater(premium_features.equity, trash_features.equity)
        self.assertGreater(premium_features.equity, 0.70)
        self.assertLess(trash_features.equity, 0.45)

    def test_pressure_weighted_opponent_model_favors_current_aggressor(self) -> None:
        aggressive = OpponentSnapshot(
            player_id="raiser",
            seat_index=1,
            chips=880,
            committed=120,
            hand_committed=120,
            folded=False,
            all_in=False,
            acted_this_round=True,
            last_action="RAISE",
            last_action_phase="TURN",
            vpip_rate=0.70,
            pfr_rate=0.45,
            aggression_factor=4.0,
            fold_to_raise_rate=0.15,
            recent_raise_rate=0.90,
        )
        passive = OpponentSnapshot(
            player_id="caller",
            seat_index=2,
            chips=1000,
            committed=0,
            hand_committed=0,
            folded=False,
            all_in=False,
            acted_this_round=False,
            last_action="CHECK",
            last_action_phase="TURN",
            vpip_rate=0.20,
            pfr_rate=0.05,
            aggression_factor=0.2,
            fold_to_raise_rate=0.55,
            recent_raise_rate=0.05,
        )
        features = extract_features(
            obs(
                phase="TURN",
                hole_cards=(c("ACE", "SPADES"), c("QUEEN", "SPADES")),
                board_cards=(c("ACE", "CLUBS"), c("TEN", "HEARTS"), c("FOUR", "DIAMONDS"), c("TWO", "CLUBS")),
                pot=300,
                current_bet=120,
                committed=0,
                legal_actions=("FOLD", "CALL"),
                opponents=(aggressive, passive),
            ),
            profile=PROFILE,
            rng=random.Random(0),
        )

        self.assertGreater(features.opponent_aggression, 0.75)
        self.assertGreater(features.recent_raise_pressure, 0.65)

    def test_preflop_unopened_premium_prefers_raise(self) -> None:
        decision = decide_action(
            obs(
                phase="PREFLOP",
                hole_cards=(c("ACE", "HEARTS"), c("KING", "HEARTS")),
                board_cards=(),
                pot=30,
                current_bet=20,
                min_raise=20,
                committed=0,
                legal_actions=("FOLD", "CALL", "RAISE", "ALL_IN"),
            ),
            profile=PROFILE,
            rng=random.Random(0),
        )

        self.assertEqual(decision.move_type, "RAISE")

    def test_preflop_facing_three_bet_marginal_hand_prefers_fold(self) -> None:
        decision = decide_action(
            obs(
                phase="PREFLOP",
                hole_cards=(c("NINE", "HEARTS"), c("SEVEN", "CLUBS")),
                board_cards=(),
                pot=150,
                current_bet=100,
                min_raise=20,
                committed=20,
                legal_actions=("FOLD", "CALL", "RAISE", "ALL_IN"),
                opponents=(
                    OpponentSnapshot(
                        player_id="raiser",
                        seat_index=1,
                        chips=900,
                        committed=100,
                        hand_committed=100,
                        folded=False,
                        all_in=False,
                        acted_this_round=True,
                        last_action="RAISE",
                        last_action_phase="PREFLOP",
                        vpip_rate=0.28,
                        pfr_rate=0.20,
                        aggression_factor=1.4,
                        fold_to_raise_rate=0.35,
                        recent_raise_rate=0.25,
                    ),
                    OpponentSnapshot(
                        player_id="re-raiser",
                        seat_index=2,
                        chips=900,
                        committed=100,
                        hand_committed=100,
                        folded=False,
                        all_in=False,
                        acted_this_round=True,
                        last_action="RAISE",
                        last_action_phase="PREFLOP",
                        vpip_rate=0.22,
                        pfr_rate=0.18,
                        aggression_factor=1.7,
                        fold_to_raise_rate=0.30,
                        recent_raise_rate=0.30,
                    ),
                ),
            ),
            profile=PROFILE,
            rng=random.Random(0),
        )

        self.assertEqual(decision.move_type, "FOLD")

    def test_preflop_short_stack_strong_hand_prefers_all_in(self) -> None:
        decision = decide_action(
            obs(
                phase="PREFLOP",
                hole_cards=(c("ACE", "HEARTS"), c("KING", "SPADES")),
                board_cards=(),
                pot=170,
                current_bet=80,
                min_raise=20,
                committed=20,
                chips=160,
                legal_actions=("FOLD", "CALL", "RAISE", "ALL_IN"),
                opponents=(
                    OpponentSnapshot(
                        player_id="raiser",
                        seat_index=1,
                        chips=920,
                        committed=80,
                        hand_committed=80,
                        folded=False,
                        all_in=False,
                        acted_this_round=True,
                        last_action="RAISE",
                        last_action_phase="PREFLOP",
                        vpip_rate=0.32,
                        pfr_rate=0.22,
                        aggression_factor=1.8,
                        fold_to_raise_rate=0.28,
                        recent_raise_rate=0.35,
                    ),
                ),
            ),
            profile=PROFILE,
            rng=random.Random(0),
        )

        self.assertEqual(decision.move_type, "ALL_IN")


class BotControllerTest(unittest.TestCase):
    def seated_heads_up_room(self) -> PokerRoom:
        room = PokerRoom("bot-test", rng=random.Random(0))
        room.join("p1", "Alice")
        room.join("bot", "Bot")
        room.sit("p1", 0)
        room.sit("bot", 1)
        room.set_ready("p1", True)
        room.set_ready("bot", True)
        room.start_hand()
        return room

    def test_build_observation_exposes_only_bot_visible_state(self) -> None:
        room = self.seated_heads_up_room()
        bot_seat = room.require_seat("bot")
        room.active_seat = bot_seat.seat_index

        observation = build_observation(room, "bot")

        self.assertEqual(observation.player_id, "bot")
        self.assertEqual(observation.hole_cards, tuple(bot_seat.hole_cards))
        self.assertEqual(observation.board_cards, tuple(room.board))
        self.assertNotIn("CHECK", observation.legal_actions)
        self.assertEqual(len(observation.opponents), 1)
        self.assertEqual(observation.opponents[0].player_id, "p1")

    def test_play_bot_turn_applies_move_through_room(self) -> None:
        room = self.seated_heads_up_room()
        bot_seat = room.require_seat("bot")
        room.active_seat = bot_seat.seat_index
        room.phase = Phase.FLOP
        room.board = [c("ACE", "CLUBS"), c("SEVEN", "DIAMONDS"), c("TWO", "SPADES")]
        bot_seat.hole_cards = [c("ACE", "HEARTS"), c("ACE", "SPADES")]
        room.current_bet = 0
        room.min_raise = 20
        room.pot = 100
        committed_before = bot_seat.hand_committed

        decision = play_bot_turn(room, "bot", profile=PROFILE, rng=random.Random(0))

        self.assertEqual(decision.move_type, "RAISE")
        self.assertGreater(bot_seat.hand_committed, committed_before)
        self.assertTrue(any("bot chose RAISE" in line for line in room.log))

    def test_room_tracks_opponent_tendencies_for_observation(self) -> None:
        room = self.seated_heads_up_room()
        room.reset_table_for_next_hand()
        room.set_ready("p1", True)
        room.set_ready("bot", True)
        room.start_hand()
        room.player_move(room.seats[room.active_seat].player_id, "CALL")
        room.player_move(room.seats[room.active_seat].player_id, "CHECK")
        room.player_move(room.seats[room.active_seat].player_id, "CHECK")
        room.player_move(room.seats[room.active_seat].player_id, "RAISE", 40)
        room.player_move(room.seats[room.active_seat].player_id, "CALL")
        room.player_move(room.seats[room.active_seat].player_id, "CHECK")
        room.player_move(room.seats[room.active_seat].player_id, "CHECK")
        room.player_move(room.seats[room.active_seat].player_id, "CHECK")
        room.player_move(room.seats[room.active_seat].player_id, "CHECK")

        room.reset_table_for_next_hand()
        room.set_ready("p1", True)
        room.set_ready("bot", True)
        room.start_hand()
        active_player_id = room.seats[room.active_seat].player_id
        room.player_move(active_player_id, "RAISE", 40)
        next_player_id = room.seats[room.active_seat].player_id
        room.player_move(next_player_id, "CALL")
        room.player_move(room.seats[room.active_seat].player_id, "CHECK")
        room.player_move(room.seats[room.active_seat].player_id, "CHECK")
        bot_seat = room.require_seat("bot")
        room.active_seat = bot_seat.seat_index

        observation = build_observation(room, "bot")
        villain = next(opponent for opponent in observation.opponents if opponent.player_id == "p1")

        self.assertGreater(villain.vpip_rate, 0.0)
        self.assertGreater(villain.pfr_rate, 0.0)
        self.assertGreater(villain.aggression_factor, 0.0)
        self.assertIn(villain.last_action, {"CHECK", "CALL", "RAISE"})


if __name__ == "__main__":
    unittest.main()
