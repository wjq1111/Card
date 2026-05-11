# Texas Holdem Online

Python-based Texas Holdem project with a gRPC server and a pygame desktop client.

## Layout

- `src/`: all runtime code
- `src/server/`: room state, chip persistence, gRPC service
- `src/client/`: pygame client UI and networking
- `src/shared/`: cards, hand evaluation, settlement, shared helpers
- `src/proto/`: source protobuf definitions
- `src/proto_gen/`: generated protobuf/grpc Python modules
- `tools/`: local build, deploy, grpc generation, rule checks, admin scripts
- `tests/`: unit and regression tests
- `docs/`: product and workflow docs
- `assets/`: future art, audio, and static content assets
- `artifacts/pyinstaller/`: generated spec plus PyInstaller build and dist outputs
- `runtime_logs/`: local logs and simple file-backed runtime state
- `docs/work-index/`: quick resume index for tools, branch gap, and next-session entry points

## Setup

Recommended Python: 3.11+

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python tools\generate_grpc.py
```

## Run

Start the server:

```powershell
python -m src.server.main
```

Start the client:

```powershell
python -m src.client.main
```

Default public server: `119.45.157.13:50051`

## Build

Build the Windows client:

```powershell
build-client.bat
```

Output:

```text
artifacts\pyinstaller\dist\TexasHoldemOnline.exe
```

## Deploy

One-click deploy from the repo root:

```powershell
deploy.bat
```

The deploy flow now works like this:

1. Build the latest local client package.
2. Auto-commit the current local snapshot if files changed.
3. Push current `HEAD` to `origin/dev` by default.
4. Try to update the server from GitHub.
5. If GitHub sync fails, fall back to local `git archive` plus `scp` upload.
6. Install dependencies, regenerate gRPC files, and restart `texas-holdem.service`.

## Validation

```powershell
python -m compileall src tools tests
python tools\check_rules.py
python -m unittest discover -s tests -v
```
