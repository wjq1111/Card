from enum import Enum

class Suit(Enum):
    NONE = 0
    SPADES = 1    # 黑桃
    HEART = 2     # 红桃
    CLUBS = 3     # 梅花
    DIAMOND = 4   # 方片

class Card:
    def __init__(self, suit, number):
        self.suit = suit
        self.number = number
        
    def __str__(self):
        suit_map = {Suit.HEART: "♥", Suit.SPADES : "♠", Suit.CLUBS: "♣", Suit.DIAMOND: "♦"}
        number_map = {1: 'A', 11: 'J', 12: 'Q', 13: 'K'}
        suit_str = suit_map.get(self.suit, str(self.suit))
        number_str = number_map.get(self.number, str(self.number))
        return f"{suit_str}{number_str}"