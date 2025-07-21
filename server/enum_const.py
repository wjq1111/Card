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
    
class ErrorCode(Enum):
    NOT_THIS_PLAYER_TURN = 0
    NOT_ENOUGH_CHIPS = 1
    CAN_NOT_CHECK_CARD = 2