param(
    [switch]$SelfTest,
    [string]$StartLlamaScript = "$PSScriptRoot\start-gemma-llama-server.ps1",
    [string]$StopLlamaScript = "$PSScriptRoot\stop-gemma-llama-server.ps1",
    [string]$HermesExe = "$env:LOCALAPPDATA\hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe",
    [string]$BaseUrl = "http://127.0.0.1:8080/v1",
    [string]$ExpectedModel = "gemma-4-12b-it",
    [string]$ExpectedModelFileName = "gemma-4-12b-it-Q6_K.gguf",
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

function Assert-PathExists {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label was not found: $Path"
    }
}

function Get-LocalLlmServerProcesses {
    Get-CimInstance Win32_Process -Filter "name = 'llama-server.exe'" |
        Where-Object {
            $_.CommandLine -like "*$ExpectedModelFileName*" -and
            $_.CommandLine -like "*--alias*$ExpectedModel*"
        }
}

function Get-OtherLauncherProcesses {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.ProcessId -ne $PID -and
            $_.Name -like "powershell*" -and
            $_.CommandLine -like "*start-hermes-desktop-with-local-llm.ps1*"
        }
}

function Test-LocalLlmServer {
    $serverProcesses = @(Get-LocalLlmServerProcesses)
    if ($serverProcesses.Count -eq 0) {
        return $false
    }

    try {
        $models = Invoke-RestMethod -Uri "$BaseUrl/models" -TimeoutSec 2
    } catch {
        return $false
    }

    foreach ($model in @($models.data)) {
        if ($model.id -eq $ExpectedModel) {
            return $true
        }
    }

    foreach ($model in @($models.models)) {
        if ($model.name -eq $ExpectedModel -or $model.model -eq $ExpectedModel) {
            return $true
        }
    }

    return $false
}

function Wait-LocalLlmServer {
    $deadline = (Get-Date).AddSeconds(180)

    while ((Get-Date) -lt $deadline) {
        if (Test-LocalLlmServer) {
            Write-LifecycleLog "Local LLM server is ready at $BaseUrl"
            return
        }

        Start-Sleep -Seconds 2
    }

    throw "Local LLM server did not become ready at $BaseUrl"
}

function Stop-LocalLlmServer {
    Assert-PathExists -Path $StopLlamaScript -Label "Stop script"
    Write-LifecycleLog "Stopping local LLM server"

    & $StopLlamaScript 2>&1 | ForEach-Object {
        Write-LifecycleLog "stop: $($_.ToString())"
    }
}

Assert-PathExists -Path $StartLlamaScript -Label "Start script"
Assert-PathExists -Path $StopLlamaScript -Label "Stop script"
Assert-PathExists -Path $HermesExe -Label "Hermes Desktop"

if ($SelfTest) {
    Write-LifecycleLog "SelfTest passed"
    Write-Host "SelfTest passed"
    exit 0
}

$otherLaunchers = @(Get-OtherLauncherProcesses)
if ($otherLaunchers.Count -gt 0) {
    Write-LifecycleLog "Another launcher is already running; exiting duplicate launcher"
    exit 0
}

try {
    Write-LifecycleLog "Lifecycle launcher started"

    if (Test-LocalLlmServer) {
        Write-LifecycleLog "Local LLM server is already ready at $BaseUrl"
    } else {
        $serverProcesses = @(Get-LocalLlmServerProcesses)
        if ($serverProcesses.Count -gt 0) {
            Write-LifecycleLog "Local LLM server process is already starting/running; pid=$($serverProcesses[0].ProcessId)"
        } else {
            Write-LifecycleLog "Starting local LLM server"
            & $StartLlamaScript 2>&1 | ForEach-Object {
                Write-LifecycleLog "start: $($_.ToString())"
            }
        }
    }

    Write-LifecycleLog "Starting Hermes Desktop"
    $hermesProcess = Start-Process `
        -FilePath $HermesExe `
        -WorkingDirectory (Split-Path -Parent $HermesExe) `
        -PassThru

    Write-LifecycleLog "Hermes Desktop started pid=$($hermesProcess.Id)"
    Start-Sleep -Seconds 5

    try {
        Wait-LocalLlmServer
    } catch {
        Write-LifecycleLog "WARNING: $($_.Exception.Message)"
    }

    Write-LifecycleLog "Waiting for launched Hermes Desktop pid=$($hermesProcess.Id) to exit"
    if (Get-Process -Id $hermesProcess.Id -ErrorAction SilentlyContinue) {
        Wait-Process -Id $hermesProcess.Id
        Write-LifecycleLog "Launched Hermes Desktop exited pid=$($hermesProcess.Id)"
    } else {
        Write-LifecycleLog "Launched Hermes Desktop already exited pid=$($hermesProcess.Id)"
    }
} catch {
    Write-LifecycleLog "ERROR: $($_.Exception.Message)"
    throw
} finally {
    try {
        Stop-LocalLlmServer
    } catch {
        Write-LifecycleLog "ERROR while stopping local LLM server: $($_.Exception.Message)"
    }

    Write-LifecycleLog "Lifecycle launcher finished"
}
