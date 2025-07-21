import time
from enum import Enum

from enum_const import StateType
from enum_const import EventResult
from enum_const import EventType
from event import Event

class Gameplay:
    pass

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

class StateBase:
    def __init__(self, state_type: StateType, gameplay: Gameplay):
        self.state_type = state_type # 状态类型
        self.enter_timestamp = time.time() # 进入这个状态的时间
        self.timeout_time = 6000000000 # 多长时间超时
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
        self.gameplay.enter_deal_cards_state()
        return super().on_enter()
    
    def on_event(self, event):
        print("deal cards state on event", event.event_type)
        if event.event_type == EventType.DEAL_CARDS_DONE:
            return EventResult.NEED_CHANGE
        return super().on_event(event)
        
class DealToFlopBetState(StateBase):
    def __init__(self, state_type, gameplay):
        super().__init__(state_type, gameplay)
    
    def on_enter(self):
        print("enter deal to flop bet state")
        self.gameplay.enter_deal_to_flop_bet_state()
        return super().on_enter()
    
    def on_event(self, event):
        print("deal to flop bet state on event", event.event_type)
        if event.event_type == EventType.PLAYER_BET:
            # 判断是不是所有人都下过注了
            if self.gameplay.is_all_player_bet_done():
                return EventResult.NEED_CHANGE
        return super().on_event(event)
    
    def on_update(self):
        # 每个人只给20000ms的最大时间，否则ai帮他操作
        self.gameplay.update_deal_to_flop_bet_state()
        return super().on_update()
        
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
