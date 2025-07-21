import random
import time
import grpc

from card import Card
from card import Suit
from player import Player
from enum_const import EventType
from enum_const import EventResult
from enum_const import StateType
from enum_const import ErrorCode

from event import Event
from proto import cs_pb2
from proto import cs_pb2_grpc

from fsm import StateMachine

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
        self.current_action_player_index = self.button_player_index # 现在该谁行动的下标 一开始默认是庄家
        self.current_min_bet = 0 # 当前最小下注
        self.current_actioned_players = [] # 当前行动过的玩家
        
        self.tick_rate = 1 # tick 30fps
        
        # 状态机 不考虑中途加入玩家 要玩就玩到底的那种
        # start -> deal cards -> bet -> flop -> bet -> turn -> bet -> river -> bet -> settle -> start ...
        self.state_machine = StateMachine(self)
        self.state_machine.init_state_machine()
        self.cur_state = StateType.INVALID
        self.event_queue = []
        
        # 通信层
        self.addr = {}
        
    # 主循环tick
    def update(self):
        return self.state_machine.update()
    
    # 处理事件
    def process_event(self, event):
        if len(self.event_queue) >= 20:
            print("queue too long")
            return
        self.event_queue.append(event)
        if len(self.event_queue) > 1:
            return
        while len(self.event_queue) > 0:
            event = self.event_queue[0]
            self.state_machine.process_event(event)
            self.event_queue = self.event_queue[1:]
    
    # 初始状态启动
    def set_start_state(self):
        if len(self.players) < 2:
            return
        self.init_gameplay()

        self.cur_state = StateType.START
        self.process_event(Event(EventType.START_GAMEPLAY))
    
    def start(self):
        while True:
            start_time = time.time()
            self.update()
            
            process_time = time.time() - start_time
            sleep_time = self.tick_rate - process_time
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                print(f"gameplay delay {-sleep_time:.4f} seconds")
            
    def stop(self):
        return

    # 初始化
    def init_gameplay(self):
        for i in range(13):
            for j in range(4):
                number = i + 1
                suit = j + 1 
                card = Card(Suit(suit), number)
                self.all_cards.append(card)
        self.all_cards = random.sample(self.all_cards, len(self.all_cards))
        
        self.status = StateType.START
    
    # 拿到牌是什么
    def get_card(self, index):
        return self.all_cards[index]
    
    # 加入玩家 
    def join_player(self, uid, name, initial_chips, ip, port):
        player = Player(uid, name, initial_chips, self)
        self.players.append(player)
        
        self.addr[uid] = ip + ":" + str(port)
        print(f"join player uid:{uid} name:{name} initial chips:{initial_chips} ip:{ip} port:{port}")
    
    def set_next_action_player(self):
        self.current_action_player_index += 1
        self.current_action_player_index = self.current_action_player_index % len(self.players)
    
    # 给玩家发手牌
    def enter_deal_cards_state(self):
        for player in self.players:
            for i in range(2):
                player.add_card(self.next_card_index)
                self.next_card_index += 1
        for player in self.players:
            print(player)
        self.process_event(Event(EventType.DEAL_CARDS_DONE))
        
    # 进入翻牌后下注
    def enter_deal_to_flop_bet_state(self):
        # 如果牌局大于2人，庄家下一位和下两位需要下注10，20，而后轮流询问（后续至少需要call 20）
        # 如果牌局只有2人，庄家下一位下注10，而后直接轮流询问（庄家需要call至少20）
        if len(self.players) < 2:
            exit(0)
        # 开局自动跳一个
        self.set_next_action_player()
        self.current_min_bet = 20
        if len(self.players) == 2:
            self.players[self.current_action_player_index].set_bet(10)
            self.set_next_action_player()
        else:
            self.players[self.current_action_player_index].set_bet(10)
            self.set_next_action_player()
            self.players[self.current_action_player_index].set_bet(20)
            self.set_next_action_player()

        self.sync_gameplay()

    # 是否所有人都下注完了
    def is_all_player_bet_done(self):
        if len(self.current_actioned_players) == len(self.players):
            return True
        return False

    # 翻牌后下注阶段更新
    def update_deal_to_flop_bet_state(self):
        pass
    
    # 玩家call注
    def player_call(self, uid):
        if self.players[self.current_action_player_index].uid != uid:
            print(f"not this player turn {uid}")
            return ErrorCode.NOT_THIS_PLAYER_TURN
        if self.players[self.current_action_player_index].chips <= self.current_min_bet:
            print(f"not enough chips {uid} {self.players[self.current_action_player_index].chips}")
            return ErrorCode.NOT_ENOUGH_CHIPS
        # call的数量是当前每个人最小的赌注-当前的赌注
        self.players[self.current_action_player_index].call(self.players[self.current_action_player_index].current_bet-self.current_min_bet)
        self.current_actioned_players.append(uid)
        self.process_event(Event(EventType.PLAYER_BET))
        self.set_next_action_player()
        
    # 玩家check
    def player_check(self, uid):
        if self.players[self.current_action_player_index].uid != uid:
            print(f"not this player turn {uid}")
            return ErrorCode.NOT_THIS_PLAYER_TURN
        if self.players[self.current_action_player_index].current_bet != self.current_min_bet:
            print(f"can't check card, should fold or call")
            return ErrorCode.CAN_NOT_CHECK_CARD
        self.players[self.current_action_player_index].check()
        self.current_actioned_players.append(uid)
        self.process_event(Event(EventType.PLAYER_BET))
        self.set_next_action_player()

    # 翻牌
    def flop_card(self):
        # 翻牌前过掉一张
        self.next_card_index += 1
        for i in range(3):
            self.flop_cards_index.append(self.next_card_index)
            self.next_card_index += 1
        
        for index in self.flop_cards_index:
            print("flop card ", self.get_card(index))
    
    # 转牌     
    def turn_card(self):
        # 转牌前过掉一张
        self.next_card_index += 1
        self.turn_card_index = self.next_card_index
        self.next_card_index += 1
        print("turn card ", self.get_card(self.turn_card_index))
    
    # 河牌
    def river_card(self):
        # 河牌前过掉一张
        self.next_card_index += 1
        self.river_card_index = self.next_card_index
        self.next_card_index += 1
        print("river card ", self.get_card(self.river_card_index))
        
    # 比大小
    def compare(self):
        return
    
    # cs交互代码
    def to_CSGameplay(self):
        player_list = []
        for i in range(len(self.players)):
            p = cs_pb2.CSGameplay.Player(uid=self.players[i].uid, index=i)
            player_list.append(p)
        
        return cs_pb2.CSGameplay(
            button_player_index=self.button_player_index,
            players=player_list
        )
    
    # 同步所有人
    def sync_gameplay(self):
        for uid in self.addr:
            channel = grpc.insecure_channel(self.addr[uid])
            stub = cs_pb2_grpc.SCStub(channel)
            stub.SyncGameplay(cs_pb2.CSReqSyncGameplay(
                uid=uid,
                gameplay=self.to_CSGameplay()
            ))
            print("sync gameplay to", uid)
        
