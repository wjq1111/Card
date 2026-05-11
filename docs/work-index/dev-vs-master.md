# Dev Vs Master

Snapshot taken from the current local `dev` branch relative to `master`.

## Branch Shape

- `master` still points to the initial Python poker project import.
- `dev` contains the active game implementation and is the branch that should keep receiving feature work.
- The `dev` branch history currently includes a long run of snapshot-style deploy commits plus a few named milestone commits.

## High-Level Gap

Compared with `master`, `dev` already contains the following major work:

- Full migration to the `src/` package layout for client, server, shared logic, protobuf source, and generated gRPC modules.
- Complete room, hand-flow, settlement, and logging implementation for Texas Holdem gameplay.
- Pygame client UI, login/lobby/room flow, and bot controls.
- Server-managed score bots plus MiniMax-backed bots with transcript logging and replay helpers.
- Chip persistence, recharge tooling, deployment automation, build scripts, and expanded repo guidance.
- Broad docs coverage for requirements, rules, deployment, bot design, MiniMax prompts, and UI exploration.
- A substantial automated test suite across room logic, hand evaluation, settlement, bots, MiniMax parsing, client UI, and rule cases.

## What This Means Operationally

- `master` is not a realistic release candidate for the current product.
- Any upcoming PR to update `master` should be based on `dev`, not rebuilt from scratch.
- Before promotion, the important work is not discovering missing product code so much as keeping `dev` tidy, validated, and documented.

## Useful Diff Commands

```powershell
git log --oneline master..dev
git diff --stat master..dev
git diff master..dev -- src tests tools docs
```

## Current Cleanup Added In This Pass

- Removed one obsolete one-off asset bootstrap script from `tools/`.
- Added this `docs/work-index/` directory so future sessions have a stable entry point for tools and branch context.
- Extended `tools/run_remote_llm_bot_match.py` so six MiniMax bots can be inspected turn by turn with ordered prompts and results.
