# AGENTS

## Repo Map

- `src/client/`: pygame client UI and networking glue
- `src/server/`: gRPC service, room state, chip persistence
- `src/shared/`: card, hand-evaluation, settlement, shared logging utilities
- `src/proto/`: source `.proto` definitions
- `src/proto_gen/`: generated Python protobuf/grpc modules
- `tools/`: local build, deploy, grpc generation, rule-check, recharge scripts
- `tests/`: unit and regression tests
- `docs/`: requirements, deployment notes, gameplay docs
- `assets/`: source assets for future art/audio/data
- `artifacts/pyinstaller/`: generated `.spec`, `build/`, `dist/`
- `runtime_logs/`: local runtime output and simple file-backed state such as player chips

## Common Tasks

- Regenerate gRPC code: `python tools\generate_grpc.py`
- Run rules and regression checks: `python tools\check_rules.py`
- Run full test suite: `python -m unittest discover -s tests -v`
- Syntax check: `python -m compileall src tools tests`
- Build Windows client: `build-client.bat`
- One-click deploy: `deploy.bat`

## Notes For Agents

- Final code imports should use `src.*` package paths. Do not add compatibility shims or duplicate root-level packages.
- Start new repo sessions from `docs/work-index/README.md` when you need the quickest overview of active tools and the current `dev`/`master` gap.
- If a deploy reaches the server but GitHub is unavailable, `tools/deploy_remote.ps1` should fall back to a local `git archive` plus `scp` upload.
- If you need to inspect the currently deployed revision on the server, check `/root/TexasHoldemOnline/.deployed_head` and `systemctl show texas-holdem.service`.
- Keep new source code under `src/`, not at the repo root.
- Do not leave temporary compatibility layers or deprecated directories in the repo. If a path is obsolete and no longer needed, remove it in the same change.
