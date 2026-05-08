---
name: texas-holdem-release-flow
description: Use for TexasHoldemOnline feature iterations, release checks, deployment, or branch promotion. Follow this when the user asks to finish a feature, validate changes, deploy to the remote server, update dev, test remote connectivity, or merge/promote dev work toward master.
---

# Texas Holdem Release Flow

Use this skill for the `E:\MyGames\TexasHoldemOnline` project when a feature iteration needs to move from local changes to remote testing and then toward `master`.

## Release Gates

Treat the flow as gated. Do not skip a later gate unless the user explicitly overrides it.

1. Local working state
   - Run `git status --short --branch`.
   - Confirm the branch is `dev` for feature work. If on `master`, switch to `dev` without discarding work.
   - Never revert unrelated user changes.

2. Local validation
   - Run Python syntax checks for touched Python files, or the whole project when broad changes occurred.
   - By default, run the relevant local tests before any deployment.
   - If the user explicitly asks to verify the latest deployed version first, run `deploy.bat` before the rule-check and test commands, then execute the same local gates and report deployment output separately.
   - Treat poker rules as a required gate for gameplay changes. After any update to room flow, action legality, hand evaluation, settlement, or related client/gRPC move handling, run the rule check suite and do not continue until it passes.
   - Keep the natural-language rule cases in `docs/poker-rule-test-cases.md` aligned with the executable checks in `tools/check_rules.py` and `tests/`.
   - For this project, useful baseline checks include:

```powershell
python -m compileall src tools tests
python tools\generate_grpc.py
python tools\check_rules.py
```

   - When the change is broad or touches multiple gameplay files, also run the full unit suite:

```powershell
python -m unittest discover -s tests -v
```

3. Commit and push to `dev`
   - Commit only after local validation passes.
   - Push to `origin/dev`, not `master`.
   - If the user has not asked for a commit, report what is ready and ask before committing.

4. Deploy remote `dev`
   - Use the project one-click deploy command from the repo root:

```bat
deploy.bat
```

   - This deploys `dev` to `119.45.157.13:/root/TexasHoldemOnline` and restarts `texas-holdem.service`.
   - It first tries to sync from GitHub, then falls back to local `git archive + scp` upload when GitHub is unavailable from the server.
   - To deploy another branch for testing, use `deploy.bat <branch>`.

5. Remote validation
   - Verify the service is active on the server.
   - Verify public TCP connectivity to `119.45.157.13:50051`.
   - When useful, run a client or gRPC smoke test against `POKER_SERVER=119.45.157.13:50051`.

6. Promote to `master`
   - Only after local validation, `dev` push, remote deploy, and remote connectivity all pass.
   - Merge or fast-forward `dev` into `master` only when the user asks or clearly approves.
   - Deploy `master` only when needed:

```bat
deploy-master.bat
```

## Reporting

End with a compact status report:

- local validation result
- `dev` push result
- remote deploy result
- remote connectivity result
- whether `master` was untouched, ready for promotion, or updated

If any gate fails, stop promotion and state the exact failing command or check.
