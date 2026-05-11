# MiniMax Bot Document Format

这套文档格式只给 MiniMax 类非交互式机器人使用，和现有 `src/server/bots/` 打分 bot 分开维护。

## 目标

1. 让服务端或工具把“当前牌面信息 + 之前所有人的公开操作”写进一个独立文档。
2. 让 MiniMax 脚本只读取这个文档的输入区。
3. 让 MiniMax 回答按固定模板写回同一个文档的输出区。

## 文档结构

文档建议使用 `.md`，并保留这四个标记：

```md
<!-- MINIMAX_BOT_INPUT_START -->
... 输入内容 ...
<!-- MINIMAX_BOT_INPUT_END -->

<!-- MINIMAX_BOT_OUTPUT_START -->
... 机器人回答 ...
<!-- MINIMAX_BOT_OUTPUT_END -->
```

## 输入区推荐格式

输入区建议直接写成结构化文本：

```text
[牌局元信息]
room_id: room-1
hand_id: room-1-000001-abcd1234
bot_id: minimax:1

[当前牌面信息]
phase: FLOP
hero_seat: 3
hero_cards: Ah Kd
board_cards: Qs Jh 2c
pot: 120
current_bet: 40
min_raise: 40
to_call: 40
chips: 1880
committed: 0
legal_actions: FOLD, CALL, RAISE, ALL_IN

[之前所有人的操作信息]
1. PREFLOP | S1 Alice | SMALL_BLIND | amount=10
2. PREFLOP | S2 Bob | BIG_BLIND | amount=20
3. PREFLOP | S3 MiniMax Bot | CALL | amount=20
```

## 输出区固定模板

模型必须严格输出：

```text
[当前牌面信息]
phase: <阶段>
hero_seat: <你的座位号，从1开始>
hero_cards: <你的手牌，未知时写 ->
board_cards: <公共牌，没有时写 ->
pot: <底池整数>
current_bet: <当前下注整数>
min_raise: <最小加注整数>
to_call: <当前需要跟注整数>
chips: <你剩余筹码整数>
committed: <你本轮已投入整数>
legal_actions: <可行动作，逗号分隔>

[之前所有人的操作信息]
1. <第1条操作>
2. <第2条操作>

[机器人决策]
move_type: <FOLD|CHECK|CALL|RAISE|ALL_IN>
amount: <整数；非RAISE时填0>
reason: <一句中文理由>
```

## 本地脚本

本地回写脚本：

```powershell
python tools\minimax_bot_document_roundtrip.py --document <path-to-doc>
```

补充说明：

`MiniMax-M2.7` 在 Anthropic 兼容接口下会返回 `thinking` 块，因此文档回写脚本默认把 `max_tokens` 提高到 `2048`，避免结构化输出被前置推理内容截断。
