from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Iterable

from shared.cards import Card, shuffled_deck
from shared.game_logging import GameLogStore, generate_hand_id
from shared.settlement import PotAward, ShowdownPlayer, ShowdownResult, settle_showdown


STARTING_CHIPS = 2000
SMALL_BLIND = 10
BIG_BLIND = 20
AUTO_START_COUNTDOWN = 3.0
HAND_COMPLETE_PAUSE = 2.0


class Phase(str, Enum):
    WAITING = "WAITING"
    PREFLOP = "PREFLOP"
    FLOP = "FLOP"
    TURN = "TURN"
    RIVER = "RIVER"
    SHOWDOWN = "SHOWDOWN"
    HAND_COMPLETE = "HAND_COMPLETE"


@dataclass
class Seat:
    seat_index: int
    player_id: str = ""
    name: str = ""
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


class PokerRoom:
    def __init__(
        self,
        room_id: str,
        seat_count: int = 6,
        *,
        logger: GameLogStore | None = None,
        auto_start_countdown: float = AUTO_START_COUNTDOWN,
        hand_complete_pause: float = HAND_COMPLETE_PAUSE,
    ) -> None:
        self.room_id = room_id
        self.players: dict[str, str] = {}
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
        self.countdown_deadline_at: float | None = None
        self.hand_complete_at: float | None = None
        self._last_countdown_value: int | None = None
        self.logger = logger
        self.auto_start_countdown = auto_start_countdown
        self.hand_complete_pause = hand_complete_pause

    def join(self, player_id: str, name: str) -> None:
        self.players[player_id] = name.strip() or "Player"
        self.log_line(f"{self.players[player_id]} joined room", event_type="ROOM")

    def leave(self, player_id: str) -> None:
        self.players.pop(player_id, None)
        seat = self.find_seat(player_id)
        if seat:
            self.clear_seat(seat)

    def sit(self, player_id: str, seat_index: int) -> None:
        if player_id not in self.players:
            raise ValueError("Player has not joined this room")
        if seat_index < 0 or seat_index >= len(self.seats):
            raise ValueError("Seat does not exist")
        if self.find_seat(player_id):
            raise ValueError("Player is already seated")
        seat = self.seats[seat_index]
        if seat.player_id:
            raise ValueError("Seat is occupied")
        seat.player_id = player_id
        seat.name = self.players[player_id]
        seat.ready = False
        self.log_line(f"{seat.name} sat down at seat {seat.seat_index + 1}", event_type="SEAT")

    def stand(self, player_id: str) -> None:
        seat = self.require_seat(player_id)
        self.clear_seat(seat)

    def set_ready(self, player_id: str, ready: bool) -> None:
        seat = self.require_seat(player_id)
        if ready and seat.chips <= 0:
            raise ValueError("Players with zero chips cannot be ready")
        seat.ready = ready
        self.log_line(f"{seat.name} is {'ready' if ready else 'not ready'}", event_type="READY")
        if self.phase == Phase.WAITING and self.ready_player_count() < 2:
            self.cancel_countdown("Not enough ready players")

    def start_hand(self) -> None:
        if self.phase not in (Phase.WAITING, Phase.HAND_COMPLETE):
            raise ValueError("A hand is already running")
        if self.phase == Phase.HAND_COMPLETE:
            self.reset_table_for_next_hand()
        active = [seat for seat in self.seats if seat.player_id and seat.ready and seat.chips > 0]
        if len(active) < 2:
            raise ValueError("At least two ready players are required")

        starting_stacks = {seat.seat_index: seat.chips for seat in self.seats}
        self.phase = Phase.PREFLOP
        self.hand_number += 1
        self.deck = shuffled_deck()
        self.board = []
        self.pot = 0
        self.current_bet = BIG_BLIND
        self.min_raise = BIG_BLIND
        self.dealer_seat = self.next_occupied_seat(self.dealer_seat)
        self.last_hand_summary = None
        self.current_hand_id = generate_hand_id(self.room_id, self.hand_number)
        self.countdown_deadline_at = None
        self.hand_complete_at = None
        self._last_countdown_value = None

        for seat in self.seats:
            seat.committed = 0
            seat.hand_committed = 0
            seat.folded = False
            seat.all_in = False
            seat.acted_this_round = False
            seat.hole_cards = self.draw(2) if seat.player_id and seat.ready else []

        active_after_deal = [seat for seat in self.seats if seat.player_id and seat.ready and seat.hole_cards]
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
            },
        )

    def update(self, now: float) -> bool:
        changed = False
        if self.phase == Phase.HAND_COMPLETE and self.hand_complete_at is not None and now >= self.hand_complete_at:
            self.reset_table_for_next_hand()
            changed = True
        if self.phase == Phase.WAITING:
            ready_count = self.ready_player_count()
            if ready_count >= 2:
                if self.countdown_deadline_at is None:
                    self.countdown_deadline_at = now + self.auto_start_countdown
                    self._last_countdown_value = self.countdown_seconds_remaining(now)
                    self.log_line(
                        f"Auto start countdown began with {ready_count} ready players",
                        event_type="COUNTDOWN",
                        data={"seconds": self._last_countdown_value},
                    )
                    changed = True
                else:
                    countdown = self.countdown_seconds_remaining(now)
                    if countdown != self._last_countdown_value:
                        self._last_countdown_value = countdown
                        changed = True
                    if now >= self.countdown_deadline_at:
                        self.start_hand()
                        changed = True
            elif self.countdown_deadline_at is not None:
                self.cancel_countdown("Ready player count dropped below two")
                changed = True
        return changed

    def player_move(self, player_id: str, move_type: str, amount: int = 0) -> None:
        seat = self.require_seat(player_id)
        if self.phase in (Phase.WAITING, Phase.HAND_COMPLETE):
            raise ValueError("No active hand")
        if seat.seat_index != self.active_seat:
            raise ValueError("It is not your turn")

        if move_type == "FOLD":
            seat.folded = True
            seat.acted_this_round = True
            self.log_line(f"{seat.name} folded", event_type="ACTION", hand_id=self.current_hand_id)
        elif move_type == "CHECK":
            if seat.committed != self.current_bet:
                raise ValueError("Cannot check facing a bet")
            seat.acted_this_round = True
            self.log_line(f"{seat.name} checked", event_type="ACTION", hand_id=self.current_hand_id)
        elif move_type == "CALL":
            self.commit(seat, self.current_bet - seat.committed)
            seat.acted_this_round = True
            self.log_line(f"{seat.name} called", event_type="ACTION", hand_id=self.current_hand_id)
        elif move_type == "RAISE":
            target_bet = amount
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
            self.log_line(f"{seat.name} moved all in", event_type="ACTION", hand_id=self.current_hand_id)
        else:
            raise ValueError("Unknown move")

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
        self.log_line(f"{self.phase.value} dealt", event_type="STREET", hand_id=self.current_hand_id)
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
        self.log_line(f"{winner.name} won {self.pot}", event_type="RESULT", hand_id=self.current_hand_id)
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
            )
        self.last_hand_summary = self.create_hand_summary(result)
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

    def clear_seat(self, seat: Seat) -> None:
        seat.player_id = ""
        seat.name = ""
        seat.ready = False
        seat.hole_cards.clear()
        seat.committed = 0
        seat.hand_committed = 0
        seat.folded = False
        seat.all_in = False
        seat.acted_this_round = False

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
        self.phase = Phase.HAND_COMPLETE
        self.active_seat = -1
        self.hand_complete_at = time.monotonic() + self.hand_complete_pause
        self.countdown_deadline_at = None
        self._last_countdown_value = None
        self.log_line(
            f"Hand {self.hand_number} completed",
            event_type="HAND_END",
            hand_id=self.current_hand_id,
            data={"winners": list(self.last_hand_summary.winner_seats) if self.last_hand_summary else []},
        )

    def reset_table_for_next_hand(self) -> None:
        self.deck = []
        self.board = []
        self.pot = 0
        self.current_bet = 0
        self.min_raise = BIG_BLIND
        self.phase = Phase.WAITING
        self.active_seat = -1
        self.hand_complete_at = None
        self.countdown_deadline_at = None
        self._last_countdown_value = None
        self.current_hand_id = ""
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

    def cancel_countdown(self, reason: str) -> None:
        self.countdown_deadline_at = None
        self._last_countdown_value = None
        self.log_line(f"Auto start countdown cancelled: {reason}", event_type="COUNTDOWN", hand_id="")

    def countdown_seconds_remaining(self, now: float) -> int:
        if self.countdown_deadline_at is None:
            return 0
        remaining = max(0.0, self.countdown_deadline_at - now)
        if remaining <= 0:
            return 0
        return int(remaining) + (0 if remaining.is_integer() else 1)
