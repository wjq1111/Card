from __future__ import annotations

from dataclasses import dataclass, replace

from src.shared.cards import Card


@dataclass(frozen=True)
class OpponentSnapshot:
    player_id: str
    seat_index: int
    chips: int
    committed: int
    hand_committed: int
    folded: bool
    all_in: bool
    acted_this_round: bool
    last_action: str
    last_action_phase: str
    vpip_rate: float
    pfr_rate: float
    aggression_factor: float
    fold_to_raise_rate: float
    recent_raise_rate: float

    def as_dict(self) -> dict[str, float | int | bool | str]:
        return {
            "player_id": self.player_id,
            "seat_index": self.seat_index,
            "chips": self.chips,
            "committed": self.committed,
            "hand_committed": self.hand_committed,
            "folded": self.folded,
            "all_in": self.all_in,
            "acted_this_round": self.acted_this_round,
            "last_action": self.last_action,
            "last_action_phase": self.last_action_phase,
            "vpip_rate": self.vpip_rate,
            "pfr_rate": self.pfr_rate,
            "aggression_factor": self.aggression_factor,
            "fold_to_raise_rate": self.fold_to_raise_rate,
            "recent_raise_rate": self.recent_raise_rate,
        }


@dataclass(frozen=True)
class BotObservation:
    player_id: str
    seat_index: int
    seat_count: int
    phase: str
    hole_cards: tuple[Card, ...]
    board_cards: tuple[Card, ...]
    pot: int
    current_bet: int
    min_raise: int
    committed: int
    chips: int
    hand_committed: int
    dealer_seat: int
    active_seat: int
    live_player_count: int
    acting_player_count: int
    legal_actions: tuple[str, ...]
    opponents: tuple[OpponentSnapshot, ...] = ()

    @property
    def to_call(self) -> int:
        return max(0, self.current_bet - self.committed)

    @property
    def stack_after_call(self) -> int:
        return max(0, self.chips - self.to_call)

    @property
    def minimum_raise_to(self) -> int:
        return self.current_bet + self.min_raise

    @property
    def maximum_raise_to(self) -> int:
        return self.committed + self.chips


@dataclass(frozen=True)
class BotProfile:
    name: str = "balanced"
    looseness: float = 0.50
    aggression: float = 0.45
    bluff_rate: float = 0.08
    risk_tolerance: float = 0.45
    randomness: float = 0.04

    def as_dict(self) -> dict[str, float | str]:
        return {
            "name": self.name,
            "looseness": self.looseness,
            "aggression": self.aggression,
            "bluff_rate": self.bluff_rate,
            "risk_tolerance": self.risk_tolerance,
            "randomness": self.randomness,
        }

    def updated(self, **changes: float | str) -> "BotProfile":
        return replace(self, **changes)


@dataclass(frozen=True)
class ScoreWeights:
    name: str = "default"
    check_made_strength: float = 0.30
    check_draw_strength: float = 0.20
    check_equity: float = 0.12
    check_position_score: float = 0.15
    check_board_wetness: float = -0.15
    check_passive_bias: float = 0.10
    call_made_strength: float = 0.35
    call_draw_strength: float = 0.30
    call_equity: float = 0.40
    call_pot_odds_fit: float = 0.45
    call_looseness: float = 0.10
    call_pressure_score: float = -0.35
    call_risk_tolerance: float = 0.10
    call_opponent_aggression: float = 0.15
    fold_pressure_score: float = 0.45
    fold_weak_made: float = 0.30
    fold_weak_draw: float = 0.20
    fold_equity: float = -0.40
    fold_pot_odds_fit: float = -0.35
    fold_looseness: float = -0.10
    fold_recent_raise_pressure: float = 0.20
    raise_value_made_strength: float = 0.45
    raise_value_board_wetness: float = 0.15
    raise_bluff_draw_strength: float = 0.30
    raise_equity: float = 0.55
    raise_bluff_position_score: float = 0.20
    raise_bluff_board_wetness: float = 0.15
    raise_opponent_fold_to_raise: float = 0.20
    raise_opponent_vpip: float = -0.10
    raise_aggression: float = 0.25
    raise_bluff_rate: float = 0.10
    raise_pressure_score: float = -0.30
    raise_size_risk: float = -0.20
    all_in_made_strength: float = 0.65
    all_in_draw_strength: float = 0.20
    all_in_equity: float = 0.80
    all_in_low_spr: float = 0.25
    all_in_risk_tolerance: float = 0.20
    all_in_aggression: float = 0.15
    all_in_bad_pot_odds: float = -0.35
    all_in_made_threshold: float = 0.72
    all_in_draw_threshold: float = 0.45
    all_in_weak_penalty: float = -0.35

    def as_dict(self) -> dict[str, float | str]:
        return self.__dict__.copy()

    def updated(self, **changes: float | str) -> "ScoreWeights":
        return replace(self, **changes)


@dataclass(frozen=True)
class BotFeatures:
    made_strength: float
    draw_strength: float
    equity: float
    pot_odds_fit: float
    position_score: float
    pressure_score: float
    spr_score: float
    board_wetness: float
    opponent_vpip: float
    opponent_pfr: float
    opponent_aggression: float
    opponent_fold_to_raise: float
    recent_raise_pressure: float

    def as_dict(self) -> dict[str, float]:
        return {
            "made_strength": self.made_strength,
            "draw_strength": self.draw_strength,
            "equity": self.equity,
            "pot_odds_fit": self.pot_odds_fit,
            "position_score": self.position_score,
            "pressure_score": self.pressure_score,
            "spr_score": self.spr_score,
            "board_wetness": self.board_wetness,
            "opponent_vpip": self.opponent_vpip,
            "opponent_pfr": self.opponent_pfr,
            "opponent_aggression": self.opponent_aggression,
            "opponent_fold_to_raise": self.opponent_fold_to_raise,
            "recent_raise_pressure": self.recent_raise_pressure,
        }


@dataclass(frozen=True)
class ActionCandidate:
    move_type: str
    amount: int = 0


@dataclass(frozen=True)
class ActionScore:
    move_type: str
    amount: int
    score: float

    def as_dict(self) -> dict[str, float | int | str]:
        return {"move_type": self.move_type, "amount": self.amount, "score": round(self.score, 4)}


@dataclass(frozen=True)
class BotDecision:
    move_type: str
    amount: int = 0
    reason: str = ""
    features: BotFeatures | None = None
    scores: tuple[ActionScore, ...] = ()
