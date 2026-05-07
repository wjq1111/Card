from __future__ import annotations

import os
import random

import pygame

from client.network import PokerClientConnection
from proto_gen import poker_pb2


WIDTH = 430
HEIGHT = 760
BG = (18, 31, 26)
FELT = (35, 88, 61)
GOLD = (232, 191, 88)
TEXT = (238, 247, 241)
MUTED = (154, 178, 166)


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Texas Holdem Online")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Microsoft YaHei UI", 20)
    small = pygame.font.SysFont("Microsoft YaHei UI", 15)

    address = os.getenv("POKER_SERVER", "localhost:50051")
    connection = PokerClientConnection(address)
    name = f"Player{random.randint(100, 999)}"
    snapshot = None
    status = f"Connecting to {address}"

    connection.send(poker_pb2.ClientEvent(join_room=poker_pb2.JoinRoom(room_id="lobby", name=name)))

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1:
                    connection.send(poker_pb2.ClientEvent(sit_down=poker_pb2.SitDown(seat_index=0)))
                elif event.key == pygame.K_2:
                    connection.send(poker_pb2.ClientEvent(sit_down=poker_pb2.SitDown(seat_index=1)))
                elif event.key == pygame.K_SPACE:
                    connection.send(poker_pb2.ClientEvent(start_hand=poker_pb2.StartHand()))
                elif event.key == pygame.K_f:
                    connection.send(poker_pb2.ClientEvent(player_move=poker_pb2.PlayerMove(type=poker_pb2.FOLD)))
                elif event.key == pygame.K_c:
                    connection.send(poker_pb2.ClientEvent(player_move=poker_pb2.PlayerMove(type=poker_pb2.CALL)))
                elif event.key == pygame.K_k:
                    connection.send(poker_pb2.ClientEvent(player_move=poker_pb2.PlayerMove(type=poker_pb2.CHECK)))
                elif event.key == pygame.K_r and snapshot:
                    amount = snapshot.current_bet + snapshot.min_raise
                    connection.send(poker_pb2.ClientEvent(player_move=poker_pb2.PlayerMove(type=poker_pb2.RAISE, amount=amount)))

        for server_event in connection.poll():
            payload = server_event.WhichOneof("payload")
            if payload == "joined":
                status = f"Joined room {server_event.joined.room_id} as {name}"
            elif payload == "snapshot":
                snapshot = server_event.snapshot
            elif payload == "error":
                status = server_event.error.message

        draw(screen, font, small, snapshot, status)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


def draw(screen, font, small, snapshot, status: str) -> None:
    width, height = screen.get_size()
    screen.fill(BG)
    pygame.draw.ellipse(screen, FELT, pygame.Rect(28, 120, width - 56, height - 230))
    draw_text(screen, font, "Texas Holdem Online", 18, 18, TEXT)
    draw_text(screen, small, status, 18, 48, MUTED)

    if not snapshot:
        draw_text(screen, font, "等待房间状态...", 120, height // 2, TEXT)
        return

    draw_text(screen, font, f"底池 {snapshot.pot}", width // 2 - 36, 150, GOLD)
    draw_cards(screen, snapshot.board, width // 2 - 145, 220)

    for index, seat in enumerate(snapshot.seats):
        x, y = seat_position(index, width, height)
        color = GOLD if seat.is_turn else (31, 44, 38)
        pygame.draw.rect(screen, color, pygame.Rect(x, y, 116, 58), border_radius=8)
        name = seat.name or f"空位 {seat.seat_index + 1}"
        chips = f"{seat.chips}" if seat.player_id else "按数字键入座"
        draw_text(screen, small, name, x + 8, y + 8, TEXT if seat.is_turn else MUTED)
        draw_text(screen, small, chips, x + 8, y + 30, TEXT if seat.is_turn else MUTED)

    draw_cards(screen, snapshot.hero_cards, width // 2 - 55, height - 170)
    draw_text(screen, small, "1/2 入座  Space 开局  F 弃牌  K 过牌  C 跟注  R 加注", 18, height - 42, MUTED)

    for line_index, line in enumerate(snapshot.log[-4:]):
        draw_text(screen, small, line, 18, height - 122 + line_index * 18, MUTED)


def draw_cards(screen, cards, x: int, y: int) -> None:
    for index in range(5):
        rect = pygame.Rect(x + index * 58, y, 48, 70)
        pygame.draw.rect(screen, (246, 239, 222), rect, border_radius=6)
        if index < len(cards):
            card = cards[index]
            label = f"{rank_label(card.rank)}{suit_label(card.suit)}"
            font = pygame.font.SysFont("Arial", 18, bold=True)
            screen.blit(font.render(label, True, (30, 30, 30)), (rect.x + 8, rect.y + 22))


def seat_position(index: int, width: int, height: int) -> tuple[int, int]:
    positions = [
        (width // 2 - 58, height - 250),
        (24, height - 360),
        (30, 180),
        (width // 2 - 58, 100),
        (width - 146, 180),
        (width - 140, height - 360),
    ]
    return positions[index % len(positions)]


def draw_text(screen, font, text: str, x: int, y: int, color) -> None:
    screen.blit(font.render(text, True, color), (x, y))


def rank_label(rank: int) -> str:
    return {
        poker_pb2.TWO: "2",
        poker_pb2.THREE: "3",
        poker_pb2.FOUR: "4",
        poker_pb2.FIVE: "5",
        poker_pb2.SIX: "6",
        poker_pb2.SEVEN: "7",
        poker_pb2.EIGHT: "8",
        poker_pb2.NINE: "9",
        poker_pb2.TEN: "T",
        poker_pb2.JACK: "J",
        poker_pb2.QUEEN: "Q",
        poker_pb2.KING: "K",
        poker_pb2.ACE: "A",
    }.get(rank, "?")


def suit_label(suit: int) -> str:
    return {
        poker_pb2.CLUBS: "C",
        poker_pb2.DIAMONDS: "D",
        poker_pb2.HEARTS: "H",
        poker_pb2.SPADES: "S",
    }.get(suit, "?")


if __name__ == "__main__":
    main()
