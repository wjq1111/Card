# Bot Scoring Model MVP Design

## 目标

第一版 bot 的目标不是成为高手，而是成为一个能稳定陪打的基础玩家：

1. 不依赖 LLM、agent、GPU 或外部推理服务。
2. 只通过服务端已有动作体系出牌：`FOLD`、`CHECK`、`CALL`、`RAISE`、`ALL_IN`。
3. 永远不绕过 `PokerRoom.player_move()` 的合法性校验。
4. 每次决策都能输出可解释的分项得分，方便后续调参和回放。
5. 先做“合理、不离谱、可测试”，再逐步提高牌力。

这套模型本质上是一个加权评分器：它会先为当前局面抽取特征，再分别给每个候选动作打分，最后选择最高分动作。它不是行为树，因为它不按固定分支写死“如果 A 就做 B”；它更像一组可调权重共同投票。

## 接入边界

建议第一版把 bot 放在服务端内部，而不是单独 RPC 服务。这样能最快跑起来，也能复用现有房间状态和动作校验。

建议新增目录：

```text
src/server/bots/
  __init__.py
  models.py
  equity.py
  features.py
  policy.py
  controller.py
```

职责划分：

1. `models.py`
   定义 `BotObservation`、`BotDecision`、`BotProfile`、`ActionScore`。

2. `features.py`
   从 `BotObservation` 提取评分特征，例如牌力、听牌、Monte Carlo equity、底池赔率、位置、SPR、牌面湿度，以及按当前施压者加权后的对手 VPIP / PFR / 激进度 / 近期加注压力。

3. `equity.py`
   用共享的牌型评估逻辑做轻量 Monte Carlo 采样，给当前局面估算真实权益。

4. `policy.py`
   对合法候选动作打分并选择动作。

5. `controller.py`
   从 `PokerRoom` 构造 `BotObservation`，调用 policy，并把结果交回 `room.player_move()`。

第一版不需要改 protobuf。bot 可以先作为服务端创建的特殊玩家加入房间，后续如果要让客户端按钮“添加 bot”，再扩展协议。

## Observation

`BotObservation` 是 bot 唯一能看到的状态。它必须只包含该座位合法可见的信息。除当前牌桌公共状态外，也可以包含基于历史公开动作汇总出来的对手画像摘要，因为这些画像并不泄露底牌信息。

```python
from dataclasses import dataclass

from src.shared.cards import Card


@dataclass(frozen=True)
class BotObservation:
    player_id: str
    seat_index: int
    seat_count: int
    phase: str
    hole_cards: tuple[Card, ...]
    board_cards: tuple[Card, ...]
    pot: int
    current_bet: int
    min_raise: int
    committed: int
    chips: int
    hand_committed: int
    dealer_seat: int
    active_seat: int
    live_player_count: int
    acting_player_count: int
    legal_actions: tuple[str, ...]
    opponents: tuple[OpponentSnapshot, ...] = ()
```

派生字段：

```python
to_call = max(0, current_bet - committed)
stack_after_call = max(0, chips - to_call)
minimum_raise_to = current_bet + min_raise
maximum_raise_to = committed + chips
```

## Decision

```python
@dataclass(frozen=True)
class BotDecision:
    move_type: str
    amount: int = 0
    reason: str = ""
```

`RAISE` 的 `amount` 表示目标下注额，和现有 `PokerRoom.player_move(player_id, "RAISE", amount)` 保持一致。

## Profile

第一版用 profile 控制“陪打性格”，避免所有 bot 都像同一个脚本。

```python
@dataclass(frozen=True)
class BotProfile:
    name: str = "balanced"
    looseness: float = 0.50
    aggression: float = 0.45
    bluff_rate: float = 0.08
    risk_tolerance: float = 0.45
    randomness: float = 0.04
```

字段含义：

1. `looseness`
   越高，越愿意用边缘牌继续。

2. `aggression`
   越高，越偏向 `RAISE` 而不是 `CALL` 或 `CHECK`。

3. `bluff_rate`
   越高，越允许弱牌在合适局面下注。

4. `risk_tolerance`
   越高，越能接受高成本跟注或全下。

5. `randomness`
   给最终分数加入轻微扰动，避免完全机械。

## 特征

所有特征归一化到 `0.0` 到 `1.0`。

### `equity`

当前实现会额外计算一个 Monte Carlo equity 特征：

```text
1. 固定 hero 手牌与已知公共牌
2. 为剩余存活对手随机发手牌
3. 随机补齐未发出的公共牌
4. 复用 `evaluate_best_hand()` 比较胜负
5. 多次采样后取平均赢池份额
```

这不是完整求解器，但比单看 `made_strength + draw_strength` 更接近真实胜率，尤其适合：

1. 翻前没有成牌时的手牌比较
2. 听牌 vs 成牌的边界局面
3. 多人池里同一牌型强度不等于真实权益的情况

### `made_strength`

当前成牌强度。第一版可以这样近似：

1. Preflop 使用起手牌强度表。
2. Flop/Turn/River 如果已有 5 张以上可评估牌，复用 `src.shared.hand_evaluator.evaluate_best_hand()`。
3. 不同牌型映射为基础分：

```text
High Card       0.12
Pair            0.35
Two Pair        0.58
Three of a Kind 0.70
Straight        0.78
Flush           0.82
Full House      0.90
Four of a Kind  0.97
Straight Flush  1.00
```

对子还要根据对子大小和踢脚修正。第一版可以简单做：

```text
Pair final = 0.25 + pair_rank / 14 * 0.20
```

### `draw_strength`

听牌潜力。第一版只识别明显听牌：

```text
Flush draw        +0.35
Open-ended draw   +0.30
Gutshot draw      +0.14
Two overcards     +0.10
```

Turn 的听牌分乘以 `0.75`，River 没有听牌分。

### `pot_odds_fit`

跟注价格是否划算：

```text
call_price = to_call
pot_after_call = pot + to_call
pot_odds = call_price / pot_after_call
estimated_equity = max(equity, made_strength * 0.55 + draw_strength * 0.45)
pot_odds_fit = clamp((estimated_equity - pot_odds + 0.25) / 0.50)
```

直觉是：权益明显高于所需赔率时接近 `1.0`，明显不够时接近 `0.0`。

### 对手特征加权

当前实现不再对所有对手做简单平均，而是优先放大“正在施压的人”：

```text
weight =
  1.0
+ 当前下注压力份额
+ 当前街最后一次 aggressive action 加权
+ 当前已顶到 current_bet 的额外权重
```

这样在多人局里，bot 不会被无关的被动玩家把桌风均值稀释掉。

### `position_score`

第一版只做粗略位置分：

```text
heads-up dealer/button 0.75
late position          0.65
middle position        0.45
early/blinds           0.30
```

后续可以基于 `dealer_seat` 和 `seat_index` 精确计算。

### `pressure_score`

行动压力，面对下注越大压力越高：

```text
to_call_ratio = to_call / max(1, chips + committed)
pressure_score = clamp(to_call_ratio * 2.5)
```

### `spr_score`

SPR 是 stack-to-pot ratio。第一版用于识别短筹码局面：

```text
spr = stack_after_call / max(1, pot + to_call)
spr_score = clamp(spr / 10)
```

`spr_score` 越低，说明越接近短筹码或承诺底池。

### `board_wetness`

牌面越湿，边缘成牌越脆弱，半诈唬和保护下注更有意义。

第一版只做三项：

```text
same_suit_3plus       +0.35
connected_ranks       +0.30
paired_board          +0.15
```

总分 clamp 到 `1.0`。

## 候选动作

当前实现从合法动作生成固定候选：

1. `FOLD`
2. `CHECK`
3. `CALL`
4. `RAISE` 到常见翻前开局/再加注档位
5. `RAISE` 到常见翻后底池比例档位
6. `ALL_IN`

翻前：

```text
open raise:
  current_bet + 1.5 * min_raise
  current_bet + 2.0 * min_raise

re-raise:
  current_bet + 2 * min_raise
  current_bet + 3 * min_raise
```

翻后：

```text
target = committed + to_call + round(pot * ratio)
ratio in {0.33, 0.50, 0.75}
```

然后统一做两步归一化：

```text
1. 先把 target 限制到 [minimum_raise_to, maximum_raise_to)
2. 再按 10 筹码粒度 round，避免 147 这类散注
```

如果归一化后达不到合法最小加注，则不生成该 `RAISE` 候选。

翻前策略不再只靠统一 sizing，而是先分层：

1. `UNOPENED`
2. `FACING_OPEN`
3. `FACING_3BET`
4. `SHORT_STACK_JAM`

每层都会对 `FOLD / CALL / RAISE / ALL_IN` 施加不同的额外修正，因此 bot 会在翻前更明显地区分：

1. 正常开池
2. 面对一次加注继续
3. 面对 3-bet 收紧范围
4. 短码下的 shove / fold 决策

## 基础权重模型

每个动作都有自己的权重。是的，这可以理解为“规定哪个行为更看重哪些因素”，但不是直接规定某个局面一定做某个行为。

### `CHECK`

```text
score_check =
  0.30 * made_strength
+ 0.20 * draw_strength
+ 0.12 * equity
+ 0.15 * position_score
- 0.15 * board_wetness
+ 0.10 * (1 - aggression)
```

解释：能免费看牌时，弱牌和听牌都可以接受 check；牌面很湿时，强牌 check 的吸引力降低。

### `CALL`

```text
score_call =
  0.35 * made_strength
+ 0.30 * draw_strength
+ 0.40 * equity
+ 0.45 * pot_odds_fit
+ 0.10 * looseness
- 0.35 * pressure_score
+ 0.10 * risk_tolerance
+ 0.15 * opponent_aggression
```

解释：call 主要由“牌是否够好”和“价格是否合理”决定。当前实现还会把对手激进度纳入考量，避免 bot 面对高频进攻型对手时过度弃牌。

### `FOLD`

```text
score_fold =
  0.45 * pressure_score
+ 0.30 * (1 - made_strength)
+ 0.20 * (1 - draw_strength)
+ fold_equity * equity
+ -0.35 * pot_odds_fit
- 0.10 * looseness
+ 0.20 * recent_raise_pressure
```

解释：fold 不是默认坏动作。面对大注、弱牌、没听牌、且桌上近期加注压力持续偏高时，它应该自然胜出。

### `RAISE`

```text
value_raise =
  0.45 * made_strength
+ 0.15 * board_wetness

semi_bluff_raise =
  0.30 * draw_strength
+ 0.20 * position_score
+ 0.15 * board_wetness

score_raise =
  value_raise
+ semi_bluff_raise
+ 0.55 * equity
+ 0.20 * opponent_fold_to_raise
- 0.10 * opponent_vpip
+ 0.25 * aggression
+ 0.10 * bluff_rate
- 0.30 * pressure_score
- 0.20 * raise_size_risk
```

`raise_size_risk`：

```text
raise_size_risk = raise_extra / max(1, chips + committed)
```

解释：raise 同时支持价值下注和半诈唬。当前实现已经把“对手是否容易弃牌”和“对手是否松跟”纳入 raise 决策，因此 bot 会对不同桌风做出有限但真实的调整。

### `ALL_IN`

```text
score_all_in =
  0.65 * made_strength
+ 0.20 * draw_strength
+ 0.80 * equity
+ 0.25 * (1 - spr_score)
+ 0.20 * risk_tolerance
+ 0.15 * aggression
- 0.35 * (1 - pot_odds_fit)
```

额外限制：

```text
if made_strength < 0.72 and draw_strength < 0.45:
    score_all_in -= 0.35
```

解释：第一版 all-in 要保守，避免陪打 bot 频繁乱推。

## Preflop 简化表

Preflop 没有 5 张牌，不能用 `evaluate_best_hand()`。第一版用起手牌强度近似：

```text
Pair:
  AA 1.00
  KK 0.96
  QQ 0.92
  JJ 0.86
  TT 0.80
  99-77 0.66
  66-22 0.50

Non-pair:
  suited broadway       0.72
  offsuit broadway      0.62
  suited ace            0.64
  offsuit ace high      0.52
  suited connectors     0.50
  two high cards        0.48
  everything else       0.25
```

位置和 looseness 可以修正：

```text
made_strength += (position_score - 0.5) * 0.12
made_strength += (looseness - 0.5) * 0.10
```

## 决策流程

```text
1. 从 PokerRoom 当前 active seat 构造 BotObservation
2. 计算 legal_actions
3. 生成候选动作和候选 raise sizing
4. 提取 features
5. 对每个候选动作计算 ActionScore
6. 加入轻微 randomness
7. 选择最高分
8. 如果输出动作被 room.player_move() 拒绝，fallback：
   - 未面对下注优先 `CHECK`
   - 面对下注优先 `CALL`
   - 其次 `FOLD`
   - 最后才是 `ALL_IN`
```

## 可解释日志

每次 bot 出手建议记录一条结构化日志：

```json
{
  "event": "BOT_DECISION",
  "bot_id": "bot_1",
  "phase": "FLOP",
  "decision": {"move_type": "RAISE", "amount": 80},
  "features": {
    "made_strength": 0.58,
    "draw_strength": 0.35,
    "pot_odds_fit": 0.62,
    "position_score": 0.65,
    "pressure_score": 0.18,
    "spr_score": 0.80,
    "board_wetness": 0.70
  },
  "scores": [
    {"move_type": "CHECK", "amount": 0, "score": 0.31},
    {"move_type": "CALL", "amount": 0, "score": 0.52},
    {"move_type": "RAISE", "amount": 80, "score": 0.61}
  ],
  "reason": "RAISE won with made hand plus wet-board protection"
}
```

这条日志是后续调参的核心。没有分项日志，权重会很快变成凭感觉拧旋钮。

## 如何判断第一版好不好

第一版验收不看“是否能赢真人”，先看四件事：

1. 合法性
   bot 连续运行多手，不能输出非法动作；即使策略输出异常，也必须 fallback 到合法动作。

2. 不离谱
   准备一批固定局面测试：
   - 面对下注时不能 `CHECK`
   - 免费行动时弱牌可以 `CHECK`
   - 强成牌倾向下注或加注
   - 明显负赔率弱牌倾向 `FOLD`
   - 明显听牌且价格便宜时倾向 `CALL`
   - `ALL_IN` 不应在弱牌低听牌局面频繁出现

3. 可解释
   每个决策都有 features 和 scores，能看出为什么选了这个动作。

4. 可回归
   固定随机种子跑同一批牌例，决策结果稳定。

## 测试建议

当前代码已经覆盖的基础测试：

```text
tests/test_bot_policy.py
```

覆盖：

1. `test_check_when_no_bet_and_weak_hand`
2. `test_fold_weak_hand_facing_large_bet`
3. `test_call_draw_with_good_pot_odds`
4. `test_raise_strong_made_hand`
5. `test_all_in_is_penalized_for_weak_hand`
6. `test_raise_amount_is_within_room_limits`

当前代码已经覆盖的控制器测试：

```text
tests/test_bot_controller.py
```

覆盖：

1. bot 只在自己行动位出手。
2. bot 决策最终通过 `room.player_move()` 应用。
3. 可观测状态只暴露 bot 合法可见信息。
4. 对手倾向统计会进入 observation。

额外已经补上的策略测试：

1. 加注候选会规整到人类常见筹码粒度。
2. 调整 `ScoreWeights` 可以翻转最终动作。
3. 高激进对手画像可以把决策从 `FOLD` 推向 `CALL`。

## 后续升级

基于当前代码状态，下一轮更值得做的是：

1. 把“当前施压者权重更高”再升级成“当前施压者 + 下注线历史”联合建模。
2. 让 Monte Carlo sample count 根据街位、多人池规模、all-in 风险自适应，而不是固定档位。
3. 把 profile / weights 外置成配置或预设，支持 `guarded`、`loose`、`nit` 等多种 bot 性格。
4. 结合 `tools/run_bot_match.py`、`tools/tune_bot_profile.py` 和 `tools/replay_hand.py` 建立固定调参回归流程。
5. 再往后考虑更重的范围估计或近似 solver，而不是直接把当前规则系统推倒重来。

## 当前试玩接入

当前客户端试玩入口默认接入一个服务端托管的 `guarded` bot。房主可在开局前点击“添加 Bot”，客户端通过现有聊天命令 `/addbot` 触发服务端创建 bot；bot 会自动入座、自动准备，并在轮到自己时等待约 1 秒后通过现有 `PokerRoom.player_move()` 链路自动行动。
