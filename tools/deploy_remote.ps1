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

$remoteScript = @'
set -euo pipefail

repo_url="$1"
branch="$2"
remote_path="$3"
service_name="$4"
restart_mode="$5"

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

if [ ! -d "$remote_path/.git" ]; then
  mkdir -p "$(dirname "$remote_path")"
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

cd "$remote_path"

before_commit="$(git rev-parse HEAD 2>/dev/null || true)"
before_pid=""
before_started=""
if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files "$service_name.service" >/dev/null 2>&1; then
  before_pid="$(systemctl show "$service_name" -p ExecMainPID --value 2>/dev/null || true)"
  before_started="$(systemctl show "$service_name" -p ExecMainStartTimestamp --value 2>/dev/null || true)"
fi

if [ ! -d ".venv" ]; then
  "$python_bin" -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python tools/generate_grpc.py

after_commit="$(git rev-parse HEAD)"
echo "Remote HEAD before deploy: ${before_commit:-unknown}"
echo "Remote HEAD after sync:    $after_commit"

if [ "$restart_mode" = "yes" ]; then
  if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files "$service_name.service" >/dev/null 2>&1; then
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

$remoteScriptPath = "/tmp/texas_holdem_deploy_$([guid]::NewGuid().ToString("N")).sh"
$uploadCommand = "cat > '$remoteScriptPath' && sed -i 's/\r$//' '$remoteScriptPath' && chmod 700 '$remoteScriptPath'"
$runCommand = "bash '$remoteScriptPath' '$RepoUrl' '$Branch' '$RemotePath' '$ServiceName' '$restartMode'; status=`$?; rm -f '$remoteScriptPath'; exit `$status"
$remoteScriptForUpload = ($remoteScript -replace "`r`n", "`n" -replace "`r", "") + "`n"

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
        Invoke-SshChecked -SshArgs $sshArgs -TargetHost $target -RemoteCommand $uploadCommand -StepName "upload deploy script" -InputText $remoteScriptForUpload
        Invoke-SshChecked -SshArgs $sshArgs -TargetHost $target -RemoteCommand $runCommand -StepName "run remote deploy" 
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
    Invoke-SshChecked -SshArgs $sshArgs -TargetHost $target -RemoteCommand $uploadCommand -StepName "upload deploy script" -InputText $remoteScriptForUpload
    Invoke-SshChecked -SshArgs $sshArgs -TargetHost $target -RemoteCommand $runCommand -StepName "run remote deploy"
}
