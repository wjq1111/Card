# Tool Inventory

This index groups the scripts under `tools/` by how they are meant to be used now.

## Core Workflow

- `generate_grpc.py`: regenerate protobuf and gRPC Python files after `src/proto/poker.proto` changes.
- `check_rules.py`: executable regression checks for gameplay rules and acceptance cases.
- `deploy_remote.ps1`: remote deployment implementation used by `deploy.bat`.
- `build_pc.ps1`: PyInstaller packaging script used by `build-client.bat`.

## Bot Evaluation And Tuning

- `run_bot_match.py`: deterministic score-bot heads-up simulation and summary output.
- `replay_hand.py`: inspect a saved hand log after suspicious or interesting outcomes.
- `tune_bot_profile.py`: mutate and evaluate profile parameters against a baseline.
- `tune_bot_weights.py`: advanced weight tuner for score-bot policy coefficients.

## MiniMax / LLM Tooling

- `run_remote_llm_bot_match.py`: live gRPC match driver with ordered MiniMax prompt/result transcripts.
- `minimax_bot_document_roundtrip.py`: feed a saved MiniMax turn document through the model and write the response back.
- `minimax_smoke_test.py`: lightweight API connectivity check for the MiniMax Anthropic-compatible endpoint.

## Operations / Admin

- `recharge_player.py`: manual chip adjustment for a named player in local runtime state.

## Removed As Obsolete

- `generate_card_assets.py`: removed because the generated SVG deck is already committed under `assets/images/cards/`, the script was not referenced by docs/tests/workflows, and it was acting as a one-off asset bootstrapper rather than an active maintenance tool.
