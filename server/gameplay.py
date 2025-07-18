from card import Card
from card import Suit

from player import Player

import random

# 一整个牌局的信息都记录在这里
class Gameplay:
    def __init__(self):
        self.players = [] # 所有玩家
        self.all_cards = [] # 所有牌 52张 初始化时候随机好，后面拿牌下标取
        self.next_card_index = 0 # 下一张要发第几张牌
        self.flop_cards_index = [] # 翻牌 存牌的下标
        self.turn_card_index = 0 # 转牌 存牌的下标
        self.river_card_index = 0 # 河牌 存牌的下标
        self.total_chips = 0 # 所有已经下注的筹码
        self.button_player_index = 0 # 庄家的玩家下标
        self.current_action_player_index = 0 # 现在该谁行动的下标
    
    # 初始化
    def init_gameplay(self):
        for i in range(13):
            for j in range(4):
                number = i + 1
                suit = j + 1 
                card = Card(Suit(suit), number)
                self.all_cards.append(card)
        self.all_cards = random.sample(self.all_cards, len(self.all_cards))
        
        # 应该要状态机 这里测试用
        self.deal_card_to_players()
    
    # 拿到牌是什么
    def get_card(self, index):
        return self.all_cards[index]
    
    # 加入玩家 
    def join_player(self, name, initial_chips):
        player = Player(name, initial_chips, self)
        self.players.append(player)
    
    # 给玩家发手牌
    def deal_card_to_players(self):
        for player in self.players:
            for i in range(2):
                player.add_card(self.next_card_index)
                self.next_card_index += 1
        
        for player in self.players:
            print(player)
    
    # 翻牌
    def flop_card(self):
        for i in range(3):
            self.flop_cards_index.append(self.next_card_index)
            self.next_card_index += 1
        
        for index in self.flop_cards_index:
            print("flop card ", self.get_card(index))
    
    # 转牌     
    def turn_card(self):
        self.turn_card_index = self.next_card_index
        self.next_card_index += 1
        print("turn card ", self.get_card(self.turn_card_index))
    
    # 河牌
    def river_card(self):
        self.river_card_index = self.next_card_index
        self.next_card_index += 1
        print("river card ", self.get_card(self.river_card_index))
        
    # 比大小
    def compare(self):
        return