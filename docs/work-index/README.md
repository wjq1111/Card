# Work Index

This directory is the quickest way to resume work in this repository.

## Start Here

1. Read [tool-inventory.md](/E:/MyGames/TexasHoldemOnline/docs/work-index/tool-inventory.md) for the current tool surface and which scripts are part of the main workflow.
2. Read [dev-vs-master.md](/E:/MyGames/TexasHoldemOnline/docs/work-index/dev-vs-master.md) for the current release gap between `dev` and `master`.
3. Use the repo-level commands below to validate changes before commit or deploy.

## Default Commands

```powershell
python -m compileall src tools tests
python tools\check_rules.py
python -m unittest discover -s tests -v
```

## Main Entry Points

- Server: `python -m src.server.main`
- Client: `python -m src.client.main`
- Deploy current `dev`: `deploy.bat`
- Build Windows client: `build-client.bat`

## High-Signal Docs

- Product requirements: [product_requirements.md](/E:/MyGames/TexasHoldemOnline/docs/product_requirements.md)
- Poker rules: [poker-rule-test-cases.md](/E:/MyGames/TexasHoldemOnline/docs/poker-rule-test-cases.md)
- Deployment notes: [deployment.md](/E:/MyGames/TexasHoldemOnline/docs/deployment.md)
- Bot tuning workflow: [bot-evaluation-and-tuning.md](/E:/MyGames/TexasHoldemOnline/docs/bot-evaluation-and-tuning.md)
- MiniMax bot transcript format: [minimax-bot-document-format.md](/E:/MyGames/TexasHoldemOnline/docs/minimax-bot-document-format.md)

## Current Branch Expectation

- Day-to-day work should continue on `dev`.
- `master` is still the initial baseline and has not been promoted with the current gameplay/client/server stack yet.
