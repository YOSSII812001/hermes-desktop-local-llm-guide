param(
    [Parameter(Mandatory = $true)]
    [int]$HermesPid,
    [string]$StopLlamaScript = "$PSScriptRoot\stop-gemma-llama-server.ps1",
    [string]$LogsDir = "$env:USERPROFILE\.hermes\logs"
)

$ErrorActionPreference = "Stop"

$LogFile = Join-Path $LogsDir "hermes-desktop-local-llm-lifecycle.log"

function Write-LifecycleLog {
    param([string]$Message)

    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LogFile -Value "[$timestamp] $Message"
}

try {
    Write-LifecycleLog "One-shot watcher waiting for Hermes Desktop pid=$HermesPid"
    if (Get-Process -Id $HermesPid -ErrorAction SilentlyContinue) {
        Wait-Process -Id $HermesPid
        Write-LifecycleLog "One-shot watcher detected Hermes Desktop exit pid=$HermesPid"
    } else {
        Write-LifecycleLog "One-shot watcher found Hermes Desktop already exited pid=$HermesPid"
    }

    if (Test-Path -LiteralPath $StopLlamaScript) {
        & $StopLlamaScript 2>&1 | ForEach-Object {
            Write-LifecycleLog "one-shot stop: $($_.ToString())"
        }
    } else {
        Write-LifecycleLog "One-shot watcher could not find stop script: $StopLlamaScript"
    }
} catch {
    Write-LifecycleLog "One-shot watcher error: $($_.Exception.Message)"
}
