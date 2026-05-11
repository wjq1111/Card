from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
import time
from typing import Callable, Iterable

from src.shared.cards import Card, shuffled_deck
from src.shared.game_logging import GameLogStore, generate_hand_id
from src.shared.settlement import PotAward, ShowdownPlayer, ShowdownResult, settle_showdown


STARTING_CHIPS = 2000
SMALL_BLIND = 10
BIG_BLIND = 20
START_GAME_COUNTDOWN = 5.0
HAND_COMPLETE_PAUSE = 2.0


class Phase(str, Enum):
    WAITING = "WAITING"
    PREFLOP = "PREFLOP"
    FLOP = "FLOP"
    TURN = "TURN"
    RIVER = "RIVER"
    SHOWDOWN = "SHOWDOWN"
    HAND_COMPLETE = "HAND_COMPLETE"


class RoomStatus(str, Enum):
    OPEN = "OPEN"
    STARTING = "STARTING"
    PLAYING = "PLAYING"


@dataclass
class Seat:
    seat_index: int
    player_id: str = ""
    name: str = ""
    avatar_id: str = ""
    chips: int = STARTING_CHIPS
    committed: int = 0
    hand_committed: int = 0
    folded: bool = False
    all_in: bool = False
    ready: bool = False
    acted_this_round: bool = False
    hole_cards: list[Card] = field(default_factory=list)


@dataclass(frozen=True)
class HandSummary:
    hand_id: str
    hand_number: int
    board: tuple[Card, ...]
    awards: tuple[PotAward, ...]
    winner_seats: tuple[int, ...]
    hand_names: dict[int, str]
    chip_deltas: dict[int, int]
    final_stacks: dict[int, int]


@dataclass
class PlayerBehaviorStats:
    hands_played: int = 0
    vpip_hands: int = 0
    pfr_hands: int = 0
    aggressive_actions: int = 0
    passive_actions: int = 0
    fold_to_raise_count: int = 0
    fold_to_raise_opportunities: int = 0
    showdown_hands: int = 0
    recent_actions: list[str] = field(default_factory=list)

    @property
    def vpip_rate(self) -> float:
        if self.hands_played <= 0:
            return 0.0
        return self.vpip_hands / self.hands_played

    @property
    def pfr_rate(self) -> float:
        if self.hands_played <= 0:
            return 0.0
        return self.pfr_hands / self.hands_played

    @property
    def aggression_factor(self) -> float:
        if self.passive_actions <= 0:
            return float(self.aggressive_actions)
        return self.aggressive_actions / self.passive_actions

    @property
    def fold_to_raise_rate(self) -> float:
        if self.fold_to_raise_opportunities <= 0:
            return 0.0
        return self.fold_to_raise_count / self.fold_to_raise_opportunities

    @property
    def recent_raise_rate(self) -> float:
        if not self.recent_actions:
            return 0.0
        raise_count = sum(1 for action in self.recent_actions if action in {"RAISE", "ALL_IN"})
        return raise_count / len(self.recent_actions)


@dataclass
class HandBehaviorState:
    voluntarily_put_money: bool = False
    preflop_raised: bool = False
    faced_raise: bool = False
    reached_showdown: bool = False
    last_action: str = ""
    last_action_phase: str = ""


@dataclass(frozen=True)
class HandActionRecord:
    player_id: str
    seat_index: int
    phase: str
    move_type: str
    amount: int
    to_call: int
    pot_before: int
    current_bet_before: int
    was_aggressive: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "player_id": self.player_id,
            "seat_index": self.seat_index,
            "phase": self.phase,
            "move_type": self.move_type,
            "amount": self.amount,
            "to_call": self.to_call,
            "pot_before": self.pot_before,
            "current_bet_before": self.current_bet_before,
            "was_aggressive": self.was_aggressive,
        }


class PokerRoom:
    def __init__(
        self,
        room_id: str,
        seat_count: int = 6,
        *,
        display_name: str = "",
        logger: GameLogStore | None = None,
        start_game_countdown: float = START_GAME_COUNTDOWN,
        hand_complete_pause: float = HAND_COMPLETE_PAUSE,
        rng: random.Random | None = None,
        chip_resolver: Callable[[str, str], int] | None = None,
        chip_persistor: Callable[[str, str, int], None] | None = None,
    ) -> None:
        self.room_id = room_id
        self.display_name = display_name or room_id
        self.players: dict[str, str] = {}
        self.player_avatars: dict[str, str] = {}
        self.owner_player_id = ""
        self.room_status = RoomStatus.OPEN
        self.seats = [Seat(seat_index=index) for index in range(seat_count)]
        self.deck: list[Card] = []
        self.board: list[Card] = []
        self.phase = Phase.WAITING
        self.pot = 0
        self.current_bet = 0
        self.min_raise = BIG_BLIND
        self.dealer_seat = -1
        self.active_seat = -1
        self.hand_number = 0
        self.log: list[str] = []
        self.last_hand_summary: HandSummary | None = None
        self.current_hand_id = ""
        self.starting_deadline_at: float | None = None
        self.hand_complete_at: float | None = None
        self._last_starting_value: int | None = None
        self.logger = logger
        self.start_game_countdown = start_game_countdown
        self.hand_complete_pause = hand_complete_pause
        self.rng = rng or random.Random()
        self.chip_resolver = chip_resolver
        self.chip_persistor = chip_persistor
        self.player_behavior: dict[str, PlayerBehaviorStats] = {}
        self.current_hand_behavior: dict[str, HandBehaviorState] = {}
        self.hand_action_log: list[HandActionRecord] = []

    def join(self, player_id: str, name: str, avatar_id: str = "") -> None:
        cleaned_name = name.strip() or "Player"
        self.players[player_id] = cleaned_name
        self.player_avatars[player_id] = avatar_id.strip()
        self.player_behavior.setdefault(player_id, PlayerBehaviorStats())
        if not self.owner_player_id:
            self.owner_player_id = player_id
        self.log_line(f"{cleaned_name} joined room", event_type="ROOM")

    def leave(self, player_id: str) -> None:
        player_name = self.players.pop(player_id, "")
        self.player_avatars.pop(player_id, None)
        seat = self.find_seat(player_id)
        if seat:
            self.sync_player_chips(player_id, seat.chips)
            self.clear_seat(seat)
        if self.owner_player_id == player_id:
            self.owner_player_id = next(iter(self.players), "")
            if self.starting_deadline_at is not None:
                self.cancel_start("Owner left the room")
        if player_name:
            self.log_line(f"{player_name} left room", event_type="ROOM")
        if self.starting_deadline_at is not None and self.ready_player_count() < 2:
            self.cancel_start("Not enough ready players")

    def is_empty(self) -> bool:
        return not self.players

    def sit(self, player_id: str, seat_index: int) -> None:
        self.assert_can_change_seat()
        self._validate_room_player(player_id)
        if seat_index < 0 or seat_index >= len(self.seats):
            raise ValueError("Seat does not exist")
        if self.find_seat(player_id):
            raise ValueError("Player is already seated")
        seat = self.seats[seat_index]
        if seat.player_id:
            raise ValueError("Seat is occupied")
        seat.player_id = player_id
        seat.name = self.players[player_id]
        seat.avatar_id = self.player_avatars.get(player_id, "")
        seat.chips = self.initial_chips_for(player_id)
        seat.ready = False
        self.log_line(f"{seat.name} sat down at seat {seat.seat_index + 1}", event_type="SEAT")

    def stand(self, player_id: str) -> None:
        self.assert_can_change_seat()
        seat = self.require_seat(player_id)
        self.clear_seat(seat)
        self.log_line(f"{self.players[player_id]} stood up", event_type="SEAT")
        self.sync_player_chips(player_id, seat.chips)

    def change_seat(self, player_id: str, seat_index: int) -> None:
        self.assert_can_change_seat()
        if seat_index < 0 or seat_index >= len(self.seats):
            raise ValueError("Seat does not exist")
        current = self.require_seat(player_id)
        target = self.seats[seat_index]
        if target.player_id:
            raise ValueError("Seat is occupied")
        current.ready = False
        target.player_id = current.player_id
        target.name = current.name
        target.avatar_id = current.avatar_id
        target.chips = current.chips
        target.ready = current.ready
        self.clear_seat(current, preserve_chips=False)
        self.log_line(f"{target.name} changed to seat {seat_index + 1}", event_type="SEAT")

    def set_ready(self, player_id: str, ready: bool) -> None:
        seat = self.require_seat(player_id)
        if self.starting_deadline_at is not None and not ready:
            raise ValueError("Cannot cancel ready after the game countdown begins")
        if ready and seat.chips <= 0:
            raise ValueError("Players with zero chips cannot be ready")
        seat.ready = ready
        self.log_line(f"{seat.name} is {'ready' if ready else 'not ready'}", event_type="READY")

    def request_start(self, player_id: str, now: float | None = None) -> None:
        if player_id != self.owner_player_id:
            raise ValueError("Only the room owner can start the game")
        if self.room_status != RoomStatus.OPEN or self.phase not in (Phase.WAITING, Phase.HAND_COMPLETE):
            raise ValueError("Room is not ready to start")
        if self.phase == Phase.HAND_COMPLETE:
            self.reset_table_for_next_hand()
        if not self.can_start():
            raise ValueError("All seated players with chips must be ready and at least two players are required")
        self.room_status = RoomStatus.STARTING
        current_time = time.monotonic() if now is None else now
        self.starting_deadline_at = current_time + self.start_game_countdown
        self._last_starting_value = self.starting_countdown_seconds(current_time)
        self.log_line(
            f"{self.players[player_id]} started the game countdown",
            event_type="COUNTDOWN",
            data={"seconds": self._last_starting_value},
        )

    def can_start(self) -> bool:
        active = self.startable_seats()
        return len(active) >= 2 and all(seat.ready for seat in active)

    def update(self, now: float) -> bool:
        changed = False
        if self.phase == Phase.HAND_COMPLETE and self.hand_complete_at is not None and now >= self.hand_complete_at:
            self.reset_table_for_next_hand()
            changed = True
        if self.room_status == RoomStatus.STARTING and self.starting_deadline_at is not None:
            if len(self.startable_seats()) < 2:
                self.cancel_start("Not enough ready players")
                return True
            countdown = self.starting_countdown_seconds(now)
            if countdown != self._last_starting_value:
                self._last_starting_value = countdown
                changed = True
            if now >= self.starting_deadline_at:
                self.start_hand()
                changed = True
        return changed

    def start_hand(self) -> None:
        active = [seat for seat in self.seats if seat.player_id and seat.ready and seat.chips > 0]
        if len(active) < 2:
            raise ValueError("At least two ready players are required")

        starting_stacks = {seat.seat_index: seat.chips for seat in self.seats}
        self.phase = Phase.PREFLOP
        self.room_status = RoomStatus.PLAYING
        self.hand_number += 1
        self.deck = shuffled_deck(self.rng)
        self.board = []
        self.pot = 0
        self.current_bet = BIG_BLIND
        self.min_raise = BIG_BLIND
        self.dealer_seat = self.rng.choice([seat.seat_index for seat in active])
        self.last_hand_summary = None
        self.current_hand_id = generate_hand_id(self.room_id, self.hand_number)
        self.starting_deadline_at = None
        self.hand_complete_at = None
        self._last_starting_value = None
        self.hand_action_log = []
        self.current_hand_behavior = {}

        for seat in self.seats:
            seat.committed = 0
            seat.hand_committed = 0
            seat.folded = False
            seat.all_in = False
            seat.acted_this_round = False
            seat.hole_cards = self.draw(2) if seat.player_id and seat.ready and seat.chips > 0 else []

        active_after_deal = [seat for seat in self.seats if seat.player_id and seat.ready and seat.hole_cards]
        for seat in active_after_deal:
            self.player_behavior.setdefault(seat.player_id, PlayerBehaviorStats()).hands_played += 1
            self.current_hand_behavior[seat.player_id] = HandBehaviorState()
        small_blind, big_blind = self.blind_seats(active_after_deal)
        self.commit(self.seats[small_blind], SMALL_BLIND)
        self.commit(self.seats[big_blind], BIG_BLIND)
        self.active_seat = self.next_action_seat(big_blind)
        self._starting_stacks = starting_stacks
        self.log_line(
            f"Hand {self.hand_number} started",
            event_type="HAND_START",
            hand_id=self.current_hand_id,
            data={
                "dealer_seat": self.dealer_seat,
                "small_blind_seat": small_blind,
                "big_blind_seat": big_blind,
                "small_blind_amount": SMALL_BLIND,
                "big_blind_amount": BIG_BLIND,
                "seats": [self.seat_snapshot_for_log(seat) for seat in self.seats if seat.player_id and seat.hole_cards],
            },
        )

    def player_move(self, player_id: str, move_type: str, amount: int = 0) -> None:
        seat = self.require_seat(player_id)
        if self.phase in (Phase.WAITING, Phase.HAND_COMPLETE):
            raise ValueError("No active hand")
        if seat.seat_index != self.active_seat:
            raise ValueError("It is not your turn")

        phase_name = self.phase.value
        to_call_before = max(0, self.current_bet - seat.committed)
        pot_before = self.pot
        current_bet_before = self.current_bet
        min_raise_before = self.min_raise
        committed_before = seat.committed
        chips_before = seat.chips
        target_bet = amount

        if move_type == "FOLD":
            seat.folded = True
            seat.acted_this_round = True
            self.log_line(
                f"{seat.name} folded",
                event_type="ACTION",
                hand_id=self.current_hand_id,
                data=self.action_log_data(
                    seat,
                    move_type,
                    amount=target_bet,
                    to_call_before=to_call_before,
                    pot_before=pot_before,
                    current_bet_before=current_bet_before,
                    min_raise_before=min_raise_before,
                    committed_before=committed_before,
                    chips_before=chips_before,
                ),
            )
        elif move_type == "CHECK":
            if seat.committed != self.current_bet:
                raise ValueError("Cannot check facing a bet")
            seat.acted_this_round = True
            self.log_line(
                f"{seat.name} checked",
                event_type="ACTION",
                hand_id=self.current_hand_id,
                data=self.action_log_data(
                    seat,
                    move_type,
                    amount=target_bet,
                    to_call_before=to_call_before,
                    pot_before=pot_before,
                    current_bet_before=current_bet_before,
                    min_raise_before=min_raise_before,
                    committed_before=committed_before,
                    chips_before=chips_before,
                ),
            )
        elif move_type == "CALL":
            self.commit(seat, self.current_bet - seat.committed)
            seat.acted_this_round = True
            self.log_line(
                f"{seat.name} called",
                event_type="ACTION",
                hand_id=self.current_hand_id,
                data=self.action_log_data(
                    seat,
                    move_type,
                    amount=target_bet,
                    to_call_before=to_call_before,
                    pot_before=pot_before,
                    current_bet_before=current_bet_before,
                    min_raise_before=min_raise_before,
                    committed_before=committed_before,
                    chips_before=chips_before,
                ),
            )
        elif move_type == "RAISE":
            if target_bet < self.current_bet + self.min_raise:
                raise ValueError("Raise is below the minimum")
            if target_bet > seat.committed + seat.chips:
                raise ValueError("Raise exceeds available chips")
            self.min_raise = target_bet - self.current_bet
            self.current_bet = target_bet
            self.commit(seat, target_bet - seat.committed)
            self.reset_action_after_raise(seat)
            self.log_line(
                f"{seat.name} raised to {target_bet}",
                event_type="ACTION",
                hand_id=self.current_hand_id,
                data=self.action_log_data(
                    seat,
                    move_type,
                    amount=target_bet,
                    to_call_before=to_call_before,
                    pot_before=pot_before,
                    current_bet_before=current_bet_before,
                    min_raise_before=min_raise_before,
                    committed_before=committed_before,
                    chips_before=chips_before,
                ),
            )
        elif move_type == "ALL_IN":
            target_bet = seat.committed + seat.chips
            self.commit(seat, seat.chips)
            seat.all_in = True
            seat.acted_this_round = True
            if target_bet >= self.current_bet + self.min_raise:
                self.min_raise = target_bet - self.current_bet
                self.current_bet = target_bet
                self.reset_action_after_raise(seat)
            elif target_bet > self.current_bet:
                self.current_bet = target_bet
            self.log_line(
                f"{seat.name} moved all in",
                event_type="ACTION",
                hand_id=self.current_hand_id,
                data=self.action_log_data(
                    seat,
                    move_type,
                    amount=target_bet,
                    to_call_before=to_call_before,
                    pot_before=pot_before,
                    current_bet_before=current_bet_before,
                    min_raise_before=min_raise_before,
                    committed_before=committed_before,
                    chips_before=chips_before,
                ),
            )
        else:
            raise ValueError("Unknown move")

        self.record_player_action(
            player_id,
            seat,
            move_type,
            phase_name=phase_name,
            amount=target_bet,
            to_call_before=to_call_before,
            pot_before=pot_before,
            current_bet_before=current_bet_before,
        )
        self.advance_after_action()

    def draw(self, count: int) -> list[Card]:
        cards = self.deck[:count]
        del self.deck[:count]
        if len(cards) != count:
            raise ValueError("Deck is empty")
        return cards

    def advance_after_action(self) -> None:
        live = [seat for seat in self.seats if seat.player_id and not seat.folded and seat.hole_cards]
        if len(live) == 1:
            self.award_uncontested_pot(live[0])
            return

        if self.betting_round_complete(live):
            self.advance_street()
            return

        self.active_seat = self.next_action_seat(self.active_seat)

    def advance_street(self) -> None:
        for seat in self.seats:
            seat.committed = 0
            seat.acted_this_round = False
        self.current_bet = 0
        self.min_raise = BIG_BLIND

        if self.phase == Phase.PREFLOP:
            self.board.extend(self.draw(3))
            self.phase = Phase.FLOP
        elif self.phase == Phase.FLOP:
            self.board.extend(self.draw(1))
            self.phase = Phase.TURN
        elif self.phase == Phase.TURN:
            self.board.extend(self.draw(1))
            self.phase = Phase.RIVER
        else:
            self.resolve_showdown()
            return

        self.active_seat = self.next_action_seat(self.dealer_seat)
        self.log_line(
            f"{self.phase.value} dealt",
            event_type="STREET",
            hand_id=self.current_hand_id,
            data={"board": [self.card_to_log(card) for card in self.board]},
        )
        live = [seat for seat in self.seats if seat.player_id and not seat.folded and seat.hole_cards]
        if self.active_seat == -1 or len([seat for seat in live if not seat.all_in]) <= 1:
            self.advance_street()

    def commit(self, seat: Seat, amount: int) -> None:
        committed = min(max(amount, 0), seat.chips)
        seat.chips -= committed
        seat.committed += committed
        seat.hand_committed += committed
        self.pot += committed
        if seat.chips == 0:
            seat.all_in = True

    def reset_action_after_raise(self, raiser: Seat) -> None:
        for seat in self.seats:
            if seat.player_id and not seat.folded and not seat.all_in and seat.hole_cards:
                seat.acted_this_round = seat.seat_index == raiser.seat_index

    def betting_round_complete(self, live: list[Seat]) -> bool:
        actionable = [seat for seat in live if not seat.all_in]
        if not actionable:
            return True
        return all(seat.acted_this_round and seat.committed == self.current_bet for seat in actionable)

    def award_uncontested_pot(self, winner: Seat) -> None:
        pot_before_award = self.pot
        winner.chips += self.pot
        self.log_line(
            f"{winner.name} won {self.pot}",
            event_type="RESULT",
            hand_id=self.current_hand_id,
            data={
                "winner_seat": winner.seat_index,
                "amount": pot_before_award,
                "board": [self.card_to_log(card) for card in self.board],
            },
        )
        self.pot = 0
        self.last_hand_summary = HandSummary(
            hand_id=self.current_hand_id,
            hand_number=self.hand_number,
            board=tuple(self.board),
            awards=(PotAward(pot_before_award, (winner.seat_index,), (winner.seat_index,)),),
            winner_seats=(winner.seat_index,),
            hand_names={},
            chip_deltas=self.chip_deltas(),
            final_stacks=self.final_stacks(),
        )
        self.sync_all_player_chips()
        self.finish_hand()

    def resolve_showdown(self) -> None:
        self.phase = Phase.SHOWDOWN
        self.active_seat = -1
        players = [
            ShowdownPlayer(
                seat_index=seat.seat_index,
                name=seat.name,
                hole_cards=tuple(seat.hole_cards),
                contribution=seat.hand_committed,
                folded=seat.folded,
            )
            for seat in self.seats
            if seat.player_id and seat.hole_cards and seat.hand_committed > 0
        ]
        result = settle_showdown(players, self.board)
        awarded = 0
        for award in result.awards:
            share, remainder = divmod(award.amount, len(award.winner_seats))
            for offset, seat_index in enumerate(award.winner_seats):
                payout = share + (1 if offset < remainder else 0)
                self.seats[seat_index].chips += payout
                awarded += payout

        self.pot = max(0, self.pot - awarded)
        for seat_index in result.winner_seats:
            hand = result.hands[seat_index]
            self.log_line(
                f"{self.seats[seat_index].name} won with {hand.name}",
                event_type="RESULT",
                hand_id=self.current_hand_id,
                data={
                    "winner_seat": seat_index,
                    "hand_name": hand.name,
                    "board": [self.card_to_log(card) for card in self.board],
                },
            )
        self.last_hand_summary = self.create_hand_summary(result)
        self.sync_all_player_chips()
        self.finish_hand()

    def blind_seats(self, active: list[Seat]) -> tuple[int, int]:
        if len(active) == 2:
            small_blind = self.dealer_seat
            big_blind = self.next_occupied_seat(small_blind)
            return small_blind, big_blind
        small_blind = self.next_occupied_seat(self.dealer_seat)
        big_blind = self.next_occupied_seat(small_blind)
        return small_blind, big_blind

    def next_occupied_seat(self, from_seat: int) -> int:
        for offset in range(1, len(self.seats) + 1):
            index = (from_seat + offset) % len(self.seats)
            seat = self.seats[index]
            if seat.player_id and seat.ready and seat.chips > 0:
                return index
        return from_seat

    def next_action_seat(self, from_seat: int) -> int:
        for offset in range(1, len(self.seats) + 1):
            index = (from_seat + offset) % len(self.seats)
            seat = self.seats[index]
            if seat.player_id and not seat.folded and not seat.all_in and seat.hole_cards:
                return index
        return -1

    def find_seat(self, player_id: str) -> Seat | None:
        return next((seat for seat in self.seats if seat.player_id == player_id), None)

    def require_seat(self, player_id: str) -> Seat:
        seat = self.find_seat(player_id)
        if not seat:
            raise ValueError("Player is not seated")
        return seat

    def clear_seat(self, seat: Seat, *, preserve_chips: bool = True) -> None:
        chips = seat.chips if preserve_chips else STARTING_CHIPS
        seat.player_id = ""
        seat.name = ""
        seat.avatar_id = ""
        seat.ready = False
        seat.hole_cards.clear()
        seat.committed = 0
        seat.hand_committed = 0
        seat.folded = False
        seat.all_in = False
        seat.acted_this_round = False
        seat.chips = chips

    def initial_chips_for(self, player_id: str) -> int:
        if self.chip_resolver is None:
            return STARTING_CHIPS
        return max(0, int(self.chip_resolver(player_id, self.players[player_id])))

    def sync_player_chips(self, player_id: str, chips: int) -> None:
        if self.chip_persistor is None or player_id not in self.players:
            return
        self.chip_persistor(player_id, self.players[player_id], max(0, int(chips)))

    def sync_all_player_chips(self) -> None:
        for seat in self.seats:
            if seat.player_id:
                self.sync_player_chips(seat.player_id, seat.chips)

    def log_line(
        self,
        message: str,
        *,
        event_type: str = "INFO",
        hand_id: str | None = None,
        data: dict[str, object] | None = None,
    ) -> None:
        self.log.append(message)
        del self.log[:-40]
        if self.logger:
            self.logger.write(
                self.room_id,
                message,
                phase=self.phase.value,
                event_type=event_type,
                hand_id=self.current_hand_id if hand_id is None else hand_id,
                hand_number=self.hand_number,
                data=data,
            )

    def card_to_log(self, card: Card) -> dict[str, str]:
        return {"rank": card.rank, "suit": card.suit}

    def cards_to_log(self, cards: Iterable[Card]) -> list[dict[str, str]]:
        return [self.card_to_log(card) for card in cards]

    def seat_snapshot_for_log(self, seat: Seat) -> dict[str, object]:
        return {
            "seat_index": seat.seat_index,
            "player_id": seat.player_id,
            "name": seat.name,
            "chips": seat.chips,
            "committed": seat.committed,
            "ready": seat.ready,
            "hole_cards": self.cards_to_log(seat.hole_cards),
        }

    def action_log_data(
        self,
        seat: Seat,
        move_type: str,
        *,
        amount: int,
        to_call_before: int,
        pot_before: int,
        current_bet_before: int,
        min_raise_before: int,
        committed_before: int,
        chips_before: int,
    ) -> dict[str, object]:
        return {
            "player_id": seat.player_id,
            "player_name": seat.name,
            "seat_index": seat.seat_index,
            "move_type": move_type,
            "amount": amount,
            "chips_put_in": self.pot - pot_before,
            "to_call_before": to_call_before,
            "pot_before": pot_before,
            "pot_after": self.pot,
            "current_bet_before": current_bet_before,
            "current_bet_after": self.current_bet,
            "min_raise_before": min_raise_before,
            "min_raise_after": self.min_raise,
            "committed_before": committed_before,
            "committed_after": seat.committed,
            "chips_before": chips_before,
            "chips_after": seat.chips,
        }

    def hand_summary_data(self) -> dict[str, object]:
        if not self.last_hand_summary:
            return {"winners": []}
        shown_hands = [
            {
                "seat_index": seat.seat_index,
                "player_id": seat.player_id,
                "player_name": seat.name,
                "hole_cards": self.cards_to_log(seat.hole_cards),
                "hand_name": self.last_hand_summary.hand_names[seat.seat_index],
            }
            for seat in self.seats
            if seat.player_id and seat.seat_index in self.last_hand_summary.hand_names
        ]
        return {
            "board": self.cards_to_log(self.last_hand_summary.board),
            "winners": list(self.last_hand_summary.winner_seats),
            "awards": [
                {
                    "amount": award.amount,
                    "winner_seats": list(award.winner_seats),
                    "eligible_seats": list(award.eligible_seats),
                }
                for award in self.last_hand_summary.awards
            ],
            "chip_deltas": self.last_hand_summary.chip_deltas,
            "final_stacks": self.last_hand_summary.final_stacks,
            "shown_hands": shown_hands,
            "actions": [record.as_dict() for record in self.hand_action_log],
        }

    def record_player_action(
        self,
        player_id: str,
        seat: Seat,
        move_type: str,
        *,
        phase_name: str,
        amount: int,
        to_call_before: int,
        pot_before: int,
        current_bet_before: int,
    ) -> None:
        stats = self.player_behavior.setdefault(player_id, PlayerBehaviorStats())
        hand_state = self.current_hand_behavior.setdefault(player_id, HandBehaviorState())
        was_aggressive = move_type == "RAISE" or (move_type == "ALL_IN" and seat.committed > current_bet_before)
        was_passive = move_type == "CALL" or (move_type == "ALL_IN" and seat.committed <= current_bet_before)
        voluntary_preflop = phase_name == Phase.PREFLOP.value and move_type in {"CALL", "RAISE", "ALL_IN"} and to_call_before > 0
        preflop_raise = phase_name == Phase.PREFLOP.value and was_aggressive

        if voluntary_preflop and not hand_state.voluntarily_put_money:
            hand_state.voluntarily_put_money = True
            stats.vpip_hands += 1
        if preflop_raise and not hand_state.preflop_raised:
            hand_state.preflop_raised = True
            stats.pfr_hands += 1
        if to_call_before > 0 and not hand_state.faced_raise:
            hand_state.faced_raise = True
            stats.fold_to_raise_opportunities += 1
        if move_type == "FOLD" and to_call_before > 0:
            stats.fold_to_raise_count += 1
        if was_aggressive:
            stats.aggressive_actions += 1
        if was_passive:
            stats.passive_actions += 1

        hand_state.last_action = move_type
        hand_state.last_action_phase = phase_name
        stats.recent_actions.append(move_type)
        del stats.recent_actions[:-12]
        self.hand_action_log.append(
            HandActionRecord(
                player_id=player_id,
                seat_index=seat.seat_index,
                phase=phase_name,
                move_type=move_type,
                amount=amount,
                to_call=to_call_before,
                pot_before=pot_before,
                current_bet_before=current_bet_before,
                was_aggressive=was_aggressive,
            )
        )
        del self.hand_action_log[:-80]

    def behavior_for_player(self, player_id: str) -> PlayerBehaviorStats:
        return self.player_behavior.setdefault(player_id, PlayerBehaviorStats())

    def hero_cards(self, player_id: str) -> Iterable[Card]:
        seat = self.find_seat(player_id)
        return seat.hole_cards if seat else []

    def create_hand_summary(self, result: ShowdownResult) -> HandSummary:
        return HandSummary(
            hand_id=self.current_hand_id,
            hand_number=self.hand_number,
            board=tuple(self.board),
            awards=result.awards,
            winner_seats=result.winner_seats,
            hand_names={seat_index: hand.name for seat_index, hand in result.hands.items()},
            chip_deltas=self.chip_deltas(),
            final_stacks=self.final_stacks(),
        )

    def chip_deltas(self) -> dict[int, int]:
        starting_stacks = getattr(self, "_starting_stacks", {})
        return {
            seat.seat_index: seat.chips - starting_stacks.get(seat.seat_index, seat.chips)
            for seat in self.seats
            if seat.player_id
        }

    def final_stacks(self) -> dict[int, int]:
        return {seat.seat_index: seat.chips for seat in self.seats if seat.player_id}

    def finish_hand(self) -> None:
        summary_data = self.hand_summary_data()
        if self.last_hand_summary:
            for seat_index in self.last_hand_summary.winner_seats:
                seat = self.seats[seat_index]
                if seat.player_id:
                    self.current_hand_behavior.setdefault(seat.player_id, HandBehaviorState()).reached_showdown = True
            for seat in self.seats:
                if seat.player_id and seat.seat_index in self.last_hand_summary.hand_names:
                    self.player_behavior.setdefault(seat.player_id, PlayerBehaviorStats()).showdown_hands += 1
        self.phase = Phase.HAND_COMPLETE
        self.room_status = RoomStatus.PLAYING
        self.active_seat = -1
        self.hand_complete_at = time.monotonic() + self.hand_complete_pause
        self.starting_deadline_at = None
        self._last_starting_value = None
        self.log_line(
            f"Hand {self.hand_number} completed",
            event_type="HAND_END",
            hand_id=self.current_hand_id,
            data=summary_data,
        )

    def reset_table_for_next_hand(self) -> None:
        self.deck = []
        self.board = []
        self.pot = 0
        self.current_bet = 0
        self.min_raise = BIG_BLIND
        self.phase = Phase.WAITING
        self.room_status = RoomStatus.OPEN
        self.active_seat = -1
        self.hand_complete_at = None
        self.starting_deadline_at = None
        self._last_starting_value = None
        self.current_hand_id = ""
        self.current_hand_behavior = {}
        self.hand_action_log = []
        for seat in self.seats:
            seat.committed = 0
            seat.hand_committed = 0
            seat.folded = False
            seat.all_in = False
            seat.acted_this_round = False
            seat.hole_cards = []
        self.log_line("Table reset for the next hand", event_type="RESET", hand_id="")

    def ready_player_count(self) -> int:
        return len([seat for seat in self.seats if seat.player_id and seat.ready and seat.chips > 0])

    def starting_countdown_seconds(self, now: float) -> int:
        if self.starting_deadline_at is None:
            return 0
        remaining = max(0.0, self.starting_deadline_at - now)
        if remaining <= 0:
            return 0
        return int(remaining) + (0 if remaining.is_integer() else 1)

    def startable_seats(self) -> list[Seat]:
        return [seat for seat in self.seats if seat.player_id and seat.chips > 0]

    def members(self) -> list[tuple[str, str, str, bool, int, bool]]:
        member_rows: list[tuple[str, str, str, bool, int, bool]] = []
        for player_id, name in self.players.items():
            seat = self.find_seat(player_id)
            member_rows.append(
                (
                    player_id,
                    name,
                    self.player_avatars.get(player_id, ""),
                    player_id == self.owner_player_id,
                    seat.seat_index if seat else -1,
                    seat.ready if seat else False,
                )
            )
        return member_rows

    def assert_can_change_seat(self) -> None:
        if self.room_status == RoomStatus.STARTING:
            raise ValueError("Seats are locked after the owner starts the game")
        if self.room_status == RoomStatus.PLAYING and self.phase != Phase.WAITING:
            raise ValueError("Cannot change seats during an active hand")

    def cancel_start(self, reason: str) -> None:
        self.starting_deadline_at = None
        self._last_starting_value = None
        self.room_status = RoomStatus.OPEN
        self.log_line(f"Game countdown cancelled: {reason}", event_type="COUNTDOWN", hand_id="")

    def _validate_room_player(self, player_id: str) -> None:
        if player_id not in self.players:
            raise ValueError("Player has not joined this room")
