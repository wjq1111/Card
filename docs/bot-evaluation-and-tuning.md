# Bot Evaluation And Tuning

## Purpose

Single-hand bot output is only a smoke test. It proves the bot can observe state,
score legal actions, and apply a move through `PokerRoom.player_move()`.

To judge whether a profile is good or bad, we need repeated, deterministic matches.

## Deterministic Match Runner

Run:

```powershell
python tools\run_bot_match.py --hands 200 --seed 7 --json
```

This runner:

1. Builds a fixed hand seed series such as `7..206`.
2. Creates one fresh `PokerRoom` per hand with `rng=random.Random(seed)`.
3. Alternates seats every hand so position bias is shared.
4. Tracks chip delta, `bb/100`, wins, and action frequencies.

The key benefit is repeatability. If we keep the same profiles and the same seed series,
the report should be identical across runs.

## How To Judge A Profile

The first practical score is:

```text
fitness = bb_per_100 - style_penalty
```

### `bb_per_100`

This is the main strategy signal. It answers:

1. Does the candidate win chips against the baseline?
2. How much does it win or lose per 100 hands in big blinds?

### `style_penalty`

This keeps the optimizer from finding weird but fragile profiles in tiny samples.

The first version penalizes:

1. all-in rate that is too high
2. raise rate that is too low
3. fold rate that is too high
4. call rate that is too low

This is not trying to enforce one perfect play style. It is only there to stop obvious
degenerate behavior from looking good because of short-run variance.

## Human-Like Tuning

After adding opponent-modeling inputs, do not tune only for `bb_per_100`. Read the
report together with the table tendencies the bot reacted to.

Use these correction rules:

1. If the bot folds too often against aggressive players, increase
   `call_opponent_aggression` or reduce `fold_recent_raise_pressure`.
2. If the bot hero-calls too much into tight players, reduce
   `call_opponent_aggression` and increase `fold_recent_raise_pressure`.
3. If the bot misses obvious steal spots against players who over-fold, increase
   `raise_opponent_fold_to_raise`.
4. If the bot bluffs too much into loose callers, make `raise_opponent_vpip` more
   negative so high-VPIP opponents discourage marginal raises.
5. If every table still produces the same action mix, change the opponent-aware
   weights before changing global `aggression`, because human-like play should adapt
   to table personality.

## Automatic Tuning

Run:

```powershell
python tools\tune_bot_profile.py --hands 200 --seed 11 --iterations 10 --candidates 6
```

The first tuning loop is intentionally simple:

1. Start from an initial `BotProfile`.
2. Evaluate it against a fixed baseline over a fixed seed set.
3. Mutate `looseness`, `aggression`, `bluff_rate`, and `risk_tolerance`.
4. Keep any mutation whose fitness is better.
5. Repeat for several iterations.

This is a deterministic local search, not a full learning system. That is enough for the
first round because it gives us a repeatable answer to a very concrete question:

“Is this profile better than the current one under the same test bench?”

## Practical Guidance

For evaluation:

1. Keep `randomness=0.0`.
2. Keep hand seeds fixed.
3. Compare the same candidate against the same baseline.
4. Run more hands before trusting small differences.

For tuning:

1. Use a fixed tuner seed so profile mutations are reproducible.
2. Treat tiny fitness changes as noise.
3. Periodically rerun the best profile on a second seed set before accepting it.
