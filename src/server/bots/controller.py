from __future__ import annotations

import random

from src.server.bots.models import BotDecision, BotObservation, BotProfile, OpponentSnapshot, ScoreWeights
from src.server.bots.policy import decide_action
from src.server.room import Phase, PokerRoom, Seat


def build_observation(room: PokerRoom, player_id: str) -> BotObservation:
    seat = room.require_seat(player_id)
    live = [row for row in room.seats if row.player_id and row.hole_cards and not row.folded]
    acting = [row for row in live if not row.all_in]
    opponents = []
    for row in room.seats:
        if not row.player_id or row.player_id == player_id:
            continue
        stats = room.behavior_for_player(row.player_id)
        hand_state = room.current_hand_behavior.get(row.player_id)
        opponents.append(
            OpponentSnapshot(
                player_id=row.player_id,
                seat_index=row.seat_index,
                chips=row.chips,
                committed=row.committed,
                hand_committed=row.hand_committed,
                folded=row.folded,
                all_in=row.all_in,
                acted_this_round=row.acted_this_round,
                last_action=hand_state.last_action if hand_state else "",
                last_action_phase=hand_state.last_action_phase if hand_state else "",
                vpip_rate=stats.vpip_rate,
                pfr_rate=stats.pfr_rate,
                aggression_factor=stats.aggression_factor,
                fold_to_raise_rate=stats.fold_to_raise_rate,
                recent_raise_rate=stats.recent_raise_rate,
            )
        )
    return BotObservation(
        player_id=player_id,
        seat_index=seat.seat_index,
        seat_count=len(room.seats),
        phase=room.phase.value,
        hole_cards=tuple(seat.hole_cards),
        board_cards=tuple(room.board),
        pot=room.pot,
        current_bet=room.current_bet,
        min_raise=room.min_raise,
        committed=seat.committed,
        chips=seat.chips,
        hand_committed=seat.hand_committed,
        dealer_seat=room.dealer_seat,
        active_seat=room.active_seat,
        live_player_count=len(live),
        acting_player_count=len(acting),
        legal_actions=legal_actions_for_seat(room, seat),
        opponents=tuple(opponents),
    )


def legal_actions_for_seat(room: PokerRoom, seat: Seat) -> tuple[str, ...]:
    if room.phase in (Phase.WAITING, Phase.HAND_COMPLETE) or seat.seat_index != room.active_seat:
        return ()

    actions: list[str] = []
    to_call = max(0, room.current_bet - seat.committed)
    if to_call > 0:
        actions.append("FOLD")
        if seat.chips > 0:
            actions.append("CALL")
    else:
        actions.append("CHECK")

    can_full_raise = seat.committed + seat.chips >= room.current_bet + room.min_raise
    if can_full_raise and seat.chips > to_call:
        actions.append("RAISE")
    if seat.chips > 0:
        actions.append("ALL_IN")
    return tuple(actions)


def play_bot_turn(
    room: PokerRoom,
    player_id: str,
    profile: BotProfile | None = None,
    weights: ScoreWeights | None = None,
    rng: random.Random | None = None,
) -> BotDecision:
    observation = build_observation(room, player_id)
    if not observation.legal_actions:
        raise ValueError("Bot cannot act from the current room state")

    decision = decide_action(observation, profile=profile, weights=weights, rng=rng)
    try:
        room.player_move(player_id, decision.move_type, decision.amount)
    except ValueError:
        decision = fallback_decision(observation)
        room.player_move(player_id, decision.move_type, decision.amount)

    log_bot_decision(room, player_id, decision)
    return decision


def fallback_decision(observation: BotObservation) -> BotDecision:
    legal = set(observation.legal_actions)
    if "CHECK" in legal:
        return BotDecision("CHECK", reason="Fallback to legal check")
    if "CALL" in legal:
        return BotDecision("CALL", reason="Fallback to legal call")
    if "FOLD" in legal:
        return BotDecision("FOLD", reason="Fallback to legal fold")
    if "ALL_IN" in legal:
        return BotDecision("ALL_IN", reason="Fallback to legal all-in")
    raise ValueError("No legal fallback action")


def log_bot_decision(room: PokerRoom, player_id: str, decision: BotDecision) -> None:
    data: dict[str, object] = {
        "bot_id": player_id,
        "decision": {"move_type": decision.move_type, "amount": decision.amount},
        "reason": decision.reason,
    }
    if decision.features:
        data["features"] = {key: round(value, 4) for key, value in decision.features.as_dict().items()}
    if decision.scores:
        data["scores"] = [score.as_dict() for score in decision.scores]
    room.log_line(
        f"{room.players.get(player_id, 'Bot')} bot chose {decision.move_type}",
        event_type="BOT_DECISION",
        hand_id=room.current_hand_id,
        data=data,
    )
