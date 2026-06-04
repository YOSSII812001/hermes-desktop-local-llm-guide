param(
    [string]$ServerExe = "$env:USERPROFILE\tools\llama.cpp-b9498-cuda-12.4\llama-server.exe",
    [string]$ModelPath = "$env:USERPROFILE\.cache\lm-studio\models\lmstudio-community\gemma-4-12B-it-GGUF\gemma-4-12b-it-Q6_K.gguf",
    [string]$Alias = "gemma-4-12b-it",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8080,
    [int]$ContextSize = 65536,
    [string]$LogsDir = "$env:USERPROFILE\.hermes\logs"
)

$ErrorActionPreference = "Stop"

$BaseUrl = "http://${HostAddress}:${Port}/v1"
$StdOutLog = Join-Path $LogsDir "llama-server-gemma.out.log"
$StdErrLog = Join-Path $LogsDir "llama-server-gemma.err.log"
$ExpectedModelFileName = Split-Path -Leaf $ModelPath

function Get-ExpectedGemmaServerProcess {
    Get-CimInstance Win32_Process -Filter "name = 'llama-server.exe'" |
        Where-Object {
            $_.CommandLine -like "*$ExpectedModelFileName*" -and
            $_.CommandLine -like "*--alias*$Alias*"
        }
}

function Get-AnyGemmaServerProcess {
    Get-CimInstance Win32_Process -Filter "name = 'llama-server.exe'" |
        Where-Object {
            $_.CommandLine -like "*gemma-4-12*-it-*.gguf*" -and
            $_.CommandLine -like "*--alias*$Alias*"
        }
}

if (-not (Test-Path -LiteralPath $ServerExe)) {
    throw "llama-server.exe was not found: $ServerExe"
}

if (-not (Test-Path -LiteralPath $ModelPath)) {
    throw "Model file was not found: $ModelPath"
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

try {
    $models = Invoke-RestMethod -Uri "$BaseUrl/models" -TimeoutSec 2
    $expectedProcesses = @(Get-ExpectedGemmaServerProcess)
    if ($expectedProcesses.Count -gt 0) {
        Write-Host "Expected Gemma llama-server is already running at $BaseUrl"
        $models | ConvertTo-Json -Depth 8
        exit 0
    }

    $oldGemmaProcesses = @(Get-AnyGemmaServerProcess)
    if ($oldGemmaProcesses.Count -gt 0) {
        foreach ($oldProcess in $oldGemmaProcesses) {
            Stop-Process -Id $oldProcess.ProcessId -Force
            Write-Host "Stopped older Gemma llama-server pid=$($oldProcess.ProcessId)"
        }
        Start-Sleep -Seconds 2
    } else {
        throw "Port ${Port} is already in use by a non-Gemma server at $BaseUrl"
    }
} catch {
    if ($_.Exception.Message -like "Port ${Port} is already in use*") {
        throw
    }
    # No server is ready yet. Continue and start llama-server.
}

$Arguments = @(
    "-m", $ModelPath,
    "--alias", $Alias,
    "--host", $HostAddress,
    "--port", [string]$Port,
    "--ctx-size", [string]$ContextSize,
    "--parallel", "1",
    "--reasoning", "off"
)

$process = Start-Process `
    -FilePath $ServerExe `
    -ArgumentList $Arguments `
    -WorkingDirectory (Split-Path -Parent $ServerExe) `
    -RedirectStandardOutput $StdOutLog `
    -RedirectStandardError $StdErrLog `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Started llama-server pid=$($process.Id)"
Write-Host "Endpoint: $BaseUrl"
Write-Host "Model alias: $Alias"
Write-Host "Model file: $ModelPath"
Write-Host "Logs: $StdOutLog"
Write-Host "Errors: $StdErrLog"
