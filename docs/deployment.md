# Remote deployment

Server: `119.45.157.13`

The deployment flow is branch based. Keep `master` stable, push unfinished work to `dev` or another test branch, then deploy that branch to the server.

## First-time server setup

The local deploy script clones the project into `/root/TexasHoldemOnline` on the server if it does not already exist.

The server needs:

- SSH access from this machine
- SSH key authentication for non-interactive deploys, or a password supplied at runtime
- `git`
- `python3.11`
- access to `https://github.com/wjq1111/Card.git`

## Deploy dev

From the project root on your local machine:

```bat
deploy.bat
```

This defaults to the `dev` branch. The underlying PowerShell command is:

```powershell
.\tools\deploy_remote.ps1 -User root -Branch dev
```

If passwordless SSH is already configured, this command can run directly without extra flags.

If the SSH user is not `root`, pass the correct user:

```powershell
.\tools\deploy_remote.ps1 -User ubuntu -Branch dev
```

If the server requires a specific private key:

```powershell
.\tools\deploy_remote.ps1 -User ubuntu -Branch dev -IdentityFile C:\Users\you\.ssh\server_key
```

If you want the script to ask for the SSH password at runtime:

```powershell
.\tools\deploy_remote.ps1 -User root -Branch dev -UsePasswordPrompt
```

You can also provide the password without editing the script:

```powershell
.\tools\deploy_remote.ps1 -User root -Branch dev -Password "new-password"
```

Or set it through an environment variable:

```powershell
$env:TEXAS_HOLDEM_DEPLOY_PASSWORD = "new-password"
.\tools\deploy_remote.ps1 -User root -Branch dev
```

## Deploy another branch

Use `-Branch` to switch the remote checkout and deploy that branch:

```bat
deploy.bat feature/table-flow
```

Or call the PowerShell script directly:

```powershell
.\tools\deploy_remote.ps1 -User ubuntu -Branch feature/table-flow
```

This lets you test a branch on the remote server without merging it into `master`.

## Deploy master

When you need to deploy `master`:

```bat
deploy-master.bat
```

## Service restart

By default the script tries to restart `texas-holdem.service` after updating code. If the service does not exist yet, the script still installs dependencies and generates gRPC code, then prints the manual start command.

To deploy without restarting:

```powershell
.\tools\deploy_remote.ps1 -User ubuntu -Branch dev -NoRestart
```

## Client connection

After the server is running, point the client at the public server:

```powershell
$env:POKER_SERVER = "119.45.157.13:50051"
python -m client.main
```
