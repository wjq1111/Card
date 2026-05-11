param(
    [string]$HostName = "119.45.157.13",
    [string]$User = "root",
    [string]$Branch = "dev",
    [string]$RepoUrl = "https://github.com/wjq1111/Card.git",
    [string]$RemotePath = "/root/TexasHoldemOnline",
    [string]$ServiceName = "texas-holdem",
    [string]$IdentityFile = "",
    [string]$Password = "",
    [int]$ConnectTimeout = 10,
    [switch]$UsePasswordPrompt,
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

$target = "$User@$HostName"
$restartMode = if ($NoRestart) { "no" } else { "yes" }

if (-not $Password -and $env:TEXAS_HOLDEM_DEPLOY_PASSWORD) {
    $Password = $env:TEXAS_HOLDEM_DEPLOY_PASSWORD
}

function Invoke-SshChecked {
    param(
        [string[]]$SshArgs,
        [string]$TargetHost,
        [string]$RemoteCommand,
        [string]$StepName,
        [string]$InputText
    )

    if ($PSBoundParameters.ContainsKey("InputText")) {
        $InputText | ssh @SshArgs $TargetHost $RemoteCommand
    }
    else {
        ssh @SshArgs $TargetHost $RemoteCommand
    }

    if ($LASTEXITCODE -ne 0) {
        throw "SSH step '$StepName' failed with exit code $LASTEXITCODE."
    }
}

function Invoke-ScpChecked {
    param(
        [string[]]$ScpArgs,
        [string]$SourcePath,
        [string]$DestinationPath,
        [string]$StepName
    )

    scp @ScpArgs $SourcePath $DestinationPath
    if ($LASTEXITCODE -ne 0) {
        throw "SCP step '$StepName' failed with exit code $LASTEXITCODE."
    }
}

$remoteScript = @'
set -euo pipefail

sync_mode="$1"
repo_url="$2"
branch="$3"
remote_path="$4"
service_name="$5"
restart_mode="$6"
expected_ref="$7"
archive_path="${8:-}"

case "$remote_path" in
  "~") remote_path="$HOME" ;;
  "~/"*) remote_path="$HOME/${remote_path#\~/}" ;;
esac

if ! command -v git >/dev/null 2>&1; then
  echo "git is not installed on the server." >&2
  exit 1
fi

python_bin=""
if command -v python3.11 >/dev/null 2>&1; then
  python_bin="python3.11"
elif command -v python3 >/dev/null 2>&1; then
  python_bin="python3"
else
  echo "python3.11 or python3 is not installed on the server." >&2
  exit 1
fi

mkdir -p "$(dirname "$remote_path")"

before_commit=""
if [ -d "$remote_path/.git" ]; then
  before_commit="$(cd "$remote_path" && git rev-parse HEAD 2>/dev/null || true)"
fi

if [ "$sync_mode" = "git" ]; then
  if [ ! -d "$remote_path/.git" ]; then
    echo "Cloning $repo_url branch $branch into $remote_path"
    git clone --branch "$branch" "$repo_url" "$remote_path"
  else
    echo "Updating $remote_path to branch $branch"
    cd "$remote_path"
    git fetch origin
    if git show-ref --verify --quiet "refs/heads/$branch"; then
      git checkout "$branch"
    else
      git checkout -B "$branch" "origin/$branch"
    fi
    git pull --ff-only origin "$branch"
  fi
elif [ "$sync_mode" = "archive" ]; then
  if [ -z "$archive_path" ] || [ ! -f "$archive_path" ]; then
    echo "Archive fallback requested but no uploaded archive was found." >&2
    exit 1
  fi

  echo "Falling back to uploaded archive sync for $expected_ref"
  mkdir -p "$remote_path"
  staging_dir="$(mktemp -d)"
  trap 'rm -rf "$staging_dir" "$archive_path"' EXIT
  tar -xzf "$archive_path" -C "$staging_dir"
  find "$remote_path" -mindepth 1 -maxdepth 1 ! -name '.git' ! -name '.venv' ! -name 'runtime_logs' ! -name 'api.key' -exec rm -rf {} +
  cp -a "$staging_dir"/. "$remote_path"/
  rm -rf "$staging_dir"
  rm -f "$archive_path"
  trap - EXIT
else
  echo "Unknown sync mode: $sync_mode" >&2
  exit 1
fi

cd "$remote_path"

if [ ! -d ".venv" ]; then
  "$python_bin" -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python tools/generate_grpc.py

repo_head="unavailable"
if [ -d ".git" ]; then
  repo_head="$(git rev-parse HEAD 2>/dev/null || true)"
fi

deployed_ref="$expected_ref"
if [ "$sync_mode" = "git" ] && [ -n "$repo_head" ] && [ "$repo_head" != "unavailable" ]; then
  deployed_ref="$repo_head"
fi
printf '%s\n' "$deployed_ref" > "$remote_path/.deployed_head"

before_pid=""
before_started=""
if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files "$service_name.service" >/dev/null 2>&1; then
  before_pid="$(systemctl show "$service_name" -p ExecMainPID --value 2>/dev/null || true)"
  before_started="$(systemctl show "$service_name" -p ExecMainStartTimestamp --value 2>/dev/null || true)"
fi

echo "Remote HEAD before deploy: ${before_commit:-unknown}"
echo "Remote repo HEAD after sync: ${repo_head:-unknown}"
echo "Deployed snapshot ref: $deployed_ref"

if [ "$restart_mode" = "yes" ]; then
  if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files "$service_name.service" >/dev/null 2>&1; then
    sudo tee "/etc/systemd/system/$service_name.service" >/dev/null <<SERVICE
[Unit]
Description=Texas Holdem Online gRPC server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$remote_path
Environment=PYTHONUNBUFFERED=1
ExecStart=$remote_path/.venv/bin/python -m src.server.main
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICE
    sudo systemctl daemon-reload
    sudo systemctl restart "$service_name"
    sudo systemctl is-active --quiet "$service_name"
    after_pid="$(systemctl show "$service_name" -p ExecMainPID --value)"
    after_started="$(systemctl show "$service_name" -p ExecMainStartTimestamp --value)"
    echo "Service PID before restart: ${before_pid:-unknown}"
    echo "Service PID after restart:  ${after_pid:-unknown}"
    echo "Service start before:       ${before_started:-unknown}"
    echo "Service start after:        ${after_started:-unknown}"
    sudo systemctl --no-pager --full status "$service_name"
  else
    echo "Service $service_name.service was not found on the server." >&2
    echo "Expected deploy flow is code update plus remote restart. Create the service or run with -NoRestart intentionally." >&2
    exit 1
  fi
else
  echo "Skipped service restart because -NoRestart was passed."
fi
'@

Write-Host "Deploying branch '$Branch' to ${target}:$RemotePath"
$sshArgs = @(
    "-o", "ConnectTimeout=$ConnectTimeout",
    "-o", "StrictHostKeyChecking=accept-new"
)

if ($IdentityFile) {
    $sshArgs += @("-i", $IdentityFile)
}

$localHead = (git rev-parse HEAD).Trim()
$remoteScriptPath = "/tmp/texas_holdem_deploy_$([guid]::NewGuid().ToString("N")).sh"
$remoteArchivePath = "/tmp/texas_holdem_bundle_$([guid]::NewGuid().ToString("N")).tar.gz"
$uploadCommand = "cat > '$remoteScriptPath' && sed -i 's/\r$//' '$remoteScriptPath' && chmod 700 '$remoteScriptPath'"
$runGitCommand = "bash '$remoteScriptPath' git '$RepoUrl' '$Branch' '$RemotePath' '$ServiceName' '$restartMode' '$localHead'; status=`$?; rm -f '$remoteScriptPath'; exit `$status"
$runArchiveCommand = "bash '$remoteScriptPath' archive '$RepoUrl' '$Branch' '$RemotePath' '$ServiceName' '$restartMode' '$localHead' '$remoteArchivePath'; status=`$?; rm -f '$remoteScriptPath' '$remoteArchivePath'; exit `$status"
$remoteScriptForUpload = ($remoteScript -replace "`r`n", "`n" -replace "`r", "") + "`n"

function Invoke-DeploySequence {
    param(
        [string[]]$ConnectionArgs
    )

    Invoke-SshChecked -SshArgs $ConnectionArgs -TargetHost $target -RemoteCommand $uploadCommand -StepName "upload deploy script" -InputText $remoteScriptForUpload
    try {
        Invoke-SshChecked -SshArgs $ConnectionArgs -TargetHost $target -RemoteCommand $runGitCommand -StepName "run remote deploy"
    }
    catch {
        Write-Warning "Git-based remote sync failed. Falling back to local archive upload."
        $localArchivePath = Join-Path $env:TEMP ("texas_holdem_bundle_" + [guid]::NewGuid().ToString("N") + ".tar.gz")
        try {
            Invoke-SshChecked -SshArgs $ConnectionArgs -TargetHost $target -RemoteCommand $uploadCommand -StepName "re-upload deploy script for archive fallback" -InputText $remoteScriptForUpload
            git archive --format=tar.gz --output="$localArchivePath" HEAD
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to create local git archive fallback bundle."
            }
            Invoke-ScpChecked -ScpArgs $ConnectionArgs -SourcePath $localArchivePath -DestinationPath "${target}:$remoteArchivePath" -StepName "upload fallback archive"
            Invoke-SshChecked -SshArgs $ConnectionArgs -TargetHost $target -RemoteCommand $runArchiveCommand -StepName "run archive deploy"
        }
        finally {
            if (Test-Path -LiteralPath $localArchivePath) {
                Remove-Item -LiteralPath $localArchivePath -Force
            }
        }
    }
}

if ($UsePasswordPrompt -or $Password) {
    if ($UsePasswordPrompt) {
        $securePassword = Read-Host "SSH password for $target" -AsSecureString
        $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
        )
    }
    else {
        $plainPassword = $Password
    }

    $askpass = Join-Path $env:TEMP ("texas_holdem_ssh_askpass_" + [guid]::NewGuid().ToString("N") + ".cmd")
    try {
        Set-Content -LiteralPath $askpass -Value "@echo $plainPassword" -Encoding ASCII
        $env:SSH_ASKPASS = $askpass
        $env:SSH_ASKPASS_REQUIRE = "force"
        $env:DISPLAY = ":0"
        Invoke-DeploySequence -ConnectionArgs $sshArgs
    }
    finally {
        $plainPassword = $null
        if (Test-Path -LiteralPath $askpass) {
            Remove-Item -LiteralPath $askpass -Force
        }
    }
}
else {
    $sshArgs += @("-o", "BatchMode=yes")
    Invoke-DeploySequence -ConnectionArgs $sshArgs
}
