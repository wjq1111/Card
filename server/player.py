class Player:
    def __init__(self, name, initial_chips, gameplay):
        self.name = name
        self.hand_card = []  # 玩家手牌
        self.chips = initial_chips  # 当前筹码数
        self.current_bet = 0  # 当前回合已下注金额
        self.folded = False  # 是否已弃牌
        self.all_in = False  # 是否全下
        self.gameplay = gameplay # 持有gameplay
    
    def __str__(self):
        str = f"{self.name} "
        for card in self.hand_card:
            str += self.gameplay.get_card(card).__str__() + " "
        return str
    
    # 增加手牌
    def add_card(self, card):
        self.hand_card.append(card)
    
    # 过牌
    def check(self):
        if self.folded:
            print(f"{self.name} already folded")
            return False
        print(f"{self.name} check")
        return True
    
    # 弃牌
    def fold(self):
        if self.folded:
            print(f"{self.name} already folded")
            return False
        self.folded = True
        self.current_bet = 0
        print(f"{self.name} fold")
        return True
    
    # 加注
    def raise_bet(self, count):
        if self.folded:
            print(f"{self.name} already folded")
            return False
        
        if count > self.chips:
            print(f"{self.name} chips not enough {count}")
            return False
        
        self.chips -= count
        self.current_bet += count
        
        # all in
        if self.chips == 0:
            self.all_in = True
            print(f"{self.name} all in")
        
        print(f"{self.name} raise {count}, current bet {self.current_bet}, rest chip {self.chips}")
        return count
    
    # 跟注
    def call(self, count_to_call):
        if self.folded:
            print(f"{self.name} already folded")
            return False
        
        # 计算实际需要跟注的金额
        actual_call = min(count_to_call, self.chips)
        
        self.chips -= actual_call
        self.current_bet += actual_call
        
        # 检查是否全下
        if actual_call == self.chips:
            self.all_in = True
            print(f"{self.name} all in")
        
        print(f"{self.name} call {actual_call}, current bet {self.current_bet}, rest chip {self.chips}")
        return actual_call
