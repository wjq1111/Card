from card import Card
from card import Suit
from player import Player

import random
import time
from enum import Enum

class StateType(Enum):
    INVALID = 0
    START = 1
    DEAL_CARDS = 2
    DEAL_TO_FLOP_BET = 3
    FLOP_CARDS = 4
    FLOP_TO_TURN_BET = 5
    TURN_CARDS = 6
    TURN_TO_RIVER_BET = 7
    RIVER_CARDS = 7
    RIVER_TO_SETTLE_BET = 8
    SETTLE = 9

class EventResult(Enum):
    NO_NEED_CHANGE = 0
    NEED_CHANGE = 1

class EventType(Enum):
    INVALID = 0
    START_GAMEPLAY = 1
    DEAL_CARDS_DONE = 2 # 初始发牌完成
    FLOP_CARDS_DONE = 3 # 翻牌发牌完成
    TURN_CARDS_DONE = 4 # 转牌发牌完成
    RIVER_CARDS_DONE = 5 # 河牌发牌完成
    PLAYER_BET = 6 # 玩家下注

class Event():
    def __init__(self, event_type: EventType):
        self.event_type = event_type

class Gameplay:
    pass

class StateBase:
    def __init__(self, state_type: StateType, gameplay: Gameplay):
        self.state_type = state_type # 状态类型
        self.enter_timestamp = time.time() # 进入这个状态的时间
        self.timeout_time = 600000 # 多长时间超时
        self.gameplay = gameplay
    
    # 进入状态
    def on_enter(self):
        return

    # 处理事件
    def on_event(self, event):
        return EventResult.NO_NEED_CHANGE
    
    # tick
    def on_update(self):
        if self.enter_timestamp + self.timeout_time <= time.time():
            # 超时事件
            print("time out")

    # 错误
    def on_error(self):
        return
    
    # 退出状态    
    def on_exit(self):
        return

class Transition:
    def __init__(self, state_type: StateType, event_type: EventType):
        self.state_type = state_type
        self.event_type = event_type
        
    def __hash__(self):
        state_hash = self._get_hashable(self.state_type)
        event_hash = self._get_hashable(self.event_type)
        return hash((state_hash, event_hash))
    
    def __eq__(self, other):
        if not isinstance(other, Transition):
            return False
        return (
            self._are_equal(self.state_type, other.state_type) and
            self._are_equal(self.event_type, other.event_type)
        )
    
    def __repr__(self):
        state_str = self._enum_to_str(self.state_type)
        event_str = self._enum_to_str(self.event_type)
        return f"Transition(state={state_str}, event={event_str})"
    
    def _get_hashable(self, value):
        if isinstance(value, Enum):
            return value.name
        return value
    
    def _are_equal(self, value1, value2):
        try:
            return value1 == value2
        except Exception:
            return False
    
    def _enum_to_str(self, value):
        if hasattr(value, 'name'):
            return value.name
        elif hasattr(value, 'value'):
            return value.value
        return str(value)
        
class StartState(StateBase):
    def __init__(self, state_type, gameplay):
        super().__init__(state_type, gameplay)
        
    def on_enter(self):
        print("enter start state")
        return super().on_enter()
    
    def on_event(self, event):
        print("start state on event", event.event_type)
        if event.event_type == EventType.START_GAMEPLAY:
            return EventResult.NEED_CHANGE
        return super().on_event(event)
        
class DealCardsState(StateBase):
    def __init__(self, state_type, gameplay):
        super().__init__(state_type, gameplay)
        
    def on_enter(self):
        print("enter deal cards state")
        self.gameplay.deal_card_to_players()
        self.gameplay.process_event(Event(EventType.DEAL_CARDS_DONE))
        return super().on_enter()
    
    def on_event(self, event):
        print("deal cards state on event", event.event_type)
        if event.event_type == EventType.DEAL_CARDS_DONE:
            return EventResult.NEED_CHANGE
        return super().on_event(event)
        
class DealToFlopBetState(StateBase):
    def __init__(self, state_type, gameplay):
        super().__init__(state_type, gameplay)
        
class FlopCardsState(StateBase):
    def __init__(self, state_type, gameplay):
        super().__init__(state_type, gameplay)

class FlopToTurnBetState(StateBase):
    def __init__(self, state_type, gameplay):
        super().__init__(state_type, gameplay)

class TurnCardsState(StateBase):
    def __init__(self, state_type, gameplay):
        super().__init__(state_type, gameplay)

class TurnToRiverBetState(StateBase):
    def __init__(self, state_type, gameplay):
        super().__init__(state_type, gameplay)

class RiverCardsState(StateBase):
    def __init__(self, state_type, gameplay):
        super().__init__(state_type, gameplay)

class RiverToSettleBetState(StateBase):
    def __init__(self, state_type, gameplay):
        super().__init__(state_type, gameplay)

class SettleState(StateBase):
    def __init__(self, state_type, gameplay):
        super().__init__(state_type, gameplay)

class StateMachine:
    def __init__(self, gameplay: Gameplay):
        self.transition_map = {}
        self.state_map = {}
        self.gameplay = gameplay
        
        self.start_state = StartState(StateType.START, self.gameplay)
        self.deal_cards_state = DealCardsState(StateType.DEAL_CARDS, self.gameplay)
        self.deal_to_flop_bet_state = DealToFlopBetState(StateType.DEAL_TO_FLOP_BET, self.gameplay)
        self.flop_cards_state = FlopCardsState(StateType.FLOP_CARDS, self.gameplay)
        self.flop_to_turn_bet_state = FlopToTurnBetState(StateType.FLOP_TO_TURN_BET, self.gameplay)
        self.turn_cards_state = TurnCardsState(StateType.TURN_CARDS, self.gameplay)
        self.turn_to_river_bet_state = TurnToRiverBetState(StateType.TURN_TO_RIVER_BET, self.gameplay)
        self.river_cards_state = RiverCardsState(StateType.RIVER_CARDS, self.gameplay)
        self.river_to_settle_bet_state = RiverToSettleBetState(StateType.RIVER_TO_SETTLE_BET, self.gameplay)
        self.settle_state = SettleState(StateType.SETTLE, self.gameplay)
    
    def init_state_machine(self):
        self.transition_map[Transition(StateType.START, EventType.START_GAMEPLAY)] = StateType.DEAL_CARDS
        self.transition_map[Transition(StateType.DEAL_CARDS, EventType.DEAL_CARDS_DONE)] = StateType.DEAL_TO_FLOP_BET
        self.transition_map[Transition(StateType.DEAL_TO_FLOP_BET, EventType.PLAYER_BET)] = StateType.FLOP_CARDS
        self.transition_map[Transition(StateType.FLOP_CARDS, EventType.FLOP_CARDS_DONE)] = StateType.FLOP_TO_TURN_BET
        self.transition_map[Transition(StateType.FLOP_TO_TURN_BET, EventType.PLAYER_BET)] = StateType.TURN_CARDS
        self.transition_map[Transition(StateType.TURN_CARDS, EventType.TURN_CARDS_DONE)] = StateType.TURN_TO_RIVER_BET
        self.transition_map[Transition(StateType.TURN_TO_RIVER_BET, EventType.PLAYER_BET)] = StateType.RIVER_CARDS
        self.transition_map[Transition(StateType.RIVER_CARDS, EventType.RIVER_CARDS_DONE)] = StateType.RIVER_TO_SETTLE_BET
        self.transition_map[Transition(StateType.RIVER_TO_SETTLE_BET, EventType.PLAYER_BET)] = StateType.SETTLE
        
        self.state_map[StateType.START] = self.start_state
        self.state_map[StateType.DEAL_CARDS] = self.deal_cards_state
        self.state_map[StateType.DEAL_TO_FLOP_BET] = self.deal_to_flop_bet_state
        self.state_map[StateType.FLOP_CARDS] = self.flop_cards_state
        self.state_map[StateType.FLOP_TO_TURN_BET] = self.flop_to_turn_bet_state
        self.state_map[StateType.TURN_CARDS] = self.turn_cards_state
        self.state_map[StateType.TURN_TO_RIVER_BET] = self.turn_to_river_bet_state
        self.state_map[StateType.RIVER_CARDS] = self.river_cards_state
        self.state_map[StateType.RIVER_TO_SETTLE_BET] = self.river_to_settle_bet_state
        self.state_map[StateType.SETTLE] = self.settle_state
    
    # 获取状态机的下一个状态
    def get_next_state(self, state_type: StateType, event_type: EventType):
        return self.transition_map[Transition(state_type, event_type)]
    
    # 获取某个状态
    def get_state(self, state_type: StateType):
        return self.state_map[state_type]
    
    # tick
    def update(self):
        if self.gameplay.cur_state == StateType.INVALID:
            return
        cur_state = self.get_state(self.gameplay.cur_state)
        return cur_state.on_update()
    
    # 处理事件
    def process_event(self, event: EventType):
        cur_state = self.get_state(self.gameplay.cur_state)
        result = cur_state.on_event(event)
        if result == EventResult.NO_NEED_CHANGE:
            return
        next_state = self.get_next_state(self.gameplay.cur_state, event.event_type)
        # 退出当前状态
        cur_state.on_exit()
        # 扭转状态
        self.gameplay.cur_state = next_state
        # 进入下一个状态
        self.get_state(next_state).on_enter()

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
        self.tick_rate = 1 # tick 30fps
        
        # 状态机 不考虑中途加入玩家 要玩就玩到底的那种
        # start -> deal cards -> bet -> flop -> bet -> turn -> bet -> river -> bet -> settle -> start ...
        self.state_machine = StateMachine(self)
        self.state_machine.init_state_machine()
        self.cur_state = StateType.INVALID
        self.event_queue = []
        
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
    def join_player(self, uid, name, initial_chips):
        player = Player(name, initial_chips, self)
        self.players.append(player)
        print(f"join player uid:{uid} name:{name} initial chips:{initial_chips}")
    
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
