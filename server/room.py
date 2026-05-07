from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from shared.cards import Card, shuffled_deck


STARTING_CHIPS = 2000
SMALL_BLIND = 10
BIG_BLIND = 20


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
    folded: bool = False
    all_in: bool = False
    ready: bool = False
    hole_cards: list[Card] = field(default_factory=list)


class PokerRoom:
    def __init__(self, room_id: str, seat_count: int = 6) -> None:
        self.room_id = room_id
        self.players: dict[str, str] = {}
        self.seats = [Seat(seat_index=index) for index in range(seat_count)]
        self.deck: list[Card] = []
        self.board: list[Card] = []
        self.phase = Phase.WAITING
        self.pot = 0
        self.current_bet = 0
        self.min_raise = BIG_BLIND
        self.dealer_seat = 0
        self.active_seat = -1
        self.hand_number = 0
        self.log: list[str] = []

    def join(self, player_id: str, name: str) -> None:
        self.players[player_id] = name.strip() or "Player"

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
        seat.ready = True
        self.log_line(f"{seat.name} sat down")

    def stand(self, player_id: str) -> None:
        seat = self.require_seat(player_id)
        self.clear_seat(seat)

    def set_ready(self, player_id: str, ready: bool) -> None:
        self.require_seat(player_id).ready = ready

    def start_hand(self) -> None:
        active = [seat for seat in self.seats if seat.player_id and seat.ready and seat.chips > 0]
        if len(active) < 2:
            raise ValueError("At least two ready players are required")

        self.phase = Phase.PREFLOP
        self.hand_number += 1
        self.deck = shuffled_deck()
        self.board = []
        self.pot = 0
        self.current_bet = BIG_BLIND
        self.min_raise = BIG_BLIND
        self.dealer_seat = self.next_occupied_seat(self.dealer_seat)

        for seat in self.seats:
            seat.committed = 0
            seat.folded = False
            seat.all_in = False
            seat.hole_cards = self.draw(2) if seat.player_id and seat.ready else []

        small_blind = self.next_occupied_seat(self.dealer_seat)
        big_blind = self.next_occupied_seat(small_blind)
        self.commit(self.seats[small_blind], SMALL_BLIND)
        self.commit(self.seats[big_blind], BIG_BLIND)
        self.active_seat = self.next_action_seat(big_blind)
        self.log_line(f"Hand {self.hand_number} started")

    def player_move(self, player_id: str, move_type: str, amount: int = 0) -> None:
        seat = self.require_seat(player_id)
        if self.phase in (Phase.WAITING, Phase.HAND_COMPLETE):
            raise ValueError("No active hand")
        if seat.seat_index != self.active_seat:
            raise ValueError("It is not your turn")

        if move_type == "FOLD":
            seat.folded = True
            self.log_line(f"{seat.name} folded")
        elif move_type == "CHECK":
            if seat.committed != self.current_bet:
                raise ValueError("Cannot check facing a bet")
            self.log_line(f"{seat.name} checked")
        elif move_type == "CALL":
            self.commit(seat, self.current_bet - seat.committed)
            self.log_line(f"{seat.name} called")
        elif move_type == "RAISE":
            target_bet = max(amount, self.current_bet + self.min_raise)
            self.min_raise = target_bet - self.current_bet
            self.current_bet = target_bet
            self.commit(seat, target_bet - seat.committed)
            self.log_line(f"{seat.name} raised to {target_bet}")
        elif move_type == "ALL_IN":
            target_bet = seat.committed + seat.chips
            self.commit(seat, seat.chips)
            seat.all_in = True
            if target_bet > self.current_bet:
                self.min_raise = target_bet - self.current_bet
                self.current_bet = target_bet
            self.log_line(f"{seat.name} moved all in")
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
            self.phase = Phase.HAND_COMPLETE
            self.active_seat = -1
            self.log_line(f"{live[0].name} won the pot")
            return

        pending = any(not seat.all_in and seat.committed < self.current_bet for seat in live)
        if not pending:
            self.advance_street()
            return

        self.active_seat = self.next_action_seat(self.active_seat)

    def advance_street(self) -> None:
        for seat in self.seats:
            seat.committed = 0
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
            self.phase = Phase.SHOWDOWN
            self.active_seat = -1
            self.log_line("Showdown reached; hand evaluator plugs in here")
            return

        self.active_seat = self.next_action_seat(self.dealer_seat)
        self.log_line(f"{self.phase.value} dealt")

    def commit(self, seat: Seat, amount: int) -> None:
        committed = min(max(amount, 0), seat.chips)
        seat.chips -= committed
        seat.committed += committed
        self.pot += committed
        if seat.chips == 0:
            seat.all_in = True

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
        seat.folded = False
        seat.all_in = False

    def log_line(self, message: str) -> None:
        self.log.append(message)

    def hero_cards(self, player_id: str) -> Iterable[Card]:
        seat = self.find_seat(player_id)
        return seat.hole_cards if seat else []
