param(
    [Parameter(Mandatory = $true)]
    [int]$HermesPid,
    [string]$ServerExe = "$env:USERPROFILE\tools\llama.cpp-b9498-cuda-12.4\llama-server.exe",
    [string]$ModelPath = "$env:USERPROFILE\.cache\lm-studio\models\google\gemma-4-12B-it-qat-q4_0-gguf\gemma-4-12b-it-qat-q4_0.gguf",
    [string]$MmprojPath = "$env:USERPROFILE\.cache\lm-studio\models\google\gemma-4-12B-it-qat-q4_0-gguf\mmproj-gemma-4-12b-it-qat-q4_0.gguf",
    [string]$Alias = "gemma-4-12b-it",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8080,
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
        & $StopLlamaScript `
            -ServerExe $ServerExe `
            -ModelPath $ModelPath `
            -MmprojPath $MmprojPath `
            -Alias $Alias `
            -HostAddress $HostAddress `
            -Port $Port 2>&1 | ForEach-Object {
            Write-LifecycleLog "one-shot stop: $($_.ToString())"
        }
    } else {
        Write-LifecycleLog "One-shot watcher could not find stop script: $StopLlamaScript"
    }
} catch {
    Write-LifecycleLog "One-shot watcher error: $($_.Exception.Message)"
}
