# MiniMax Bot Turn Example

<!-- MINIMAX_BOT_INPUT_START -->
[牌局元信息]
room_id: room-demo
hand_id: room-demo-000001-abcd1234
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
4. FLOP | S1 Alice | CHECK | amount=0
5. FLOP | S2 Bob | BET | amount=40
<!-- MINIMAX_BOT_INPUT_END -->

<!-- MINIMAX_BOT_OUTPUT_START -->
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
4. FLOP | S1 Alice | CHECK | amount=0
5. FLOP | S2 Bob | BET | amount=40

[机器人决策]
move_type: CALL
amount: 0
reason: 手牌AhKd在翻牌QsJh2c形成后门顺子听牌和坚果同花听牌潜力，底池120对下注40获得3:1良好底池赔率，跟注保持手牌范围并保留在转牌圈获取价值的机会。
<!-- MINIMAX_BOT_OUTPUT_END -->
