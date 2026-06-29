param(
    [string]$ServerExe = "$env:USERPROFILE\tools\llama.cpp-b9498-cuda-12.4\llama-server.exe",
    [string]$ModelPath = "$env:USERPROFILE\.cache\lm-studio\models\google\gemma-4-12B-it-qat-q4_0-gguf\gemma-4-12b-it-qat-q4_0.gguf",
    [string]$MmprojPath = "",
    [string]$Alias = "gemma-4-12b-it",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8080,
    [int]$ContextSize = 262144,
    [string]$LogsDir = "$env:USERPROFILE\.hermes\logs",
    [ValidateSet("on", "off", "auto")]
    [string]$Reasoning = "on",
    [int]$ReasoningBudget = -1,
    [ValidateSet("auto", "none", "deepseek", "deepseek-legacy")]
    [string]$ReasoningFormat = "deepseek",
    [ValidateSet("f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1")]
    [string]$CacheTypeK = "q8_0",
    [ValidateSet("f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1")]
    [string]$CacheTypeV = "q8_0"
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
            $_.CommandLine -like "*--alias*gemma-4-12b-it*"
        }
}

if (-not (Test-Path -LiteralPath $ServerExe)) {
    throw "llama-server.exe was not found: $ServerExe"
}

if (-not (Test-Path -LiteralPath $ModelPath)) {
    throw "Model file was not found: $ModelPath"
}

# Gemma 4 is multimodal. To accept image input, llama-server must also load the
# vision projector (mmproj) GGUF via --mmproj. Without it the server starts in
# text-only mode and silently ignores images.
#
# The mmproj file name differs between distributions (official QAT ships
# mmproj-model-f16.gguf, others use mmproj-BF16.gguf, etc.), so when no explicit
# -MmprojPath is given we auto-discover any mmproj*.gguf next to the model file.
function Resolve-MmprojPath {
    param(
        [string]$ExplicitPath,
        [string]$ModelFilePath
    )

    if ($ExplicitPath) {
        if (Test-Path -LiteralPath $ExplicitPath) {
            return $ExplicitPath
        }
        Write-Warning "Specified mmproj was not found: $ExplicitPath"
        return ""
    }

    $modelDir = Split-Path -Parent $ModelFilePath
    if (-not (Test-Path -LiteralPath $modelDir -PathType Container)) {
        return ""
    }

    # Prefer higher-precision projectors when several are present: f16 > bf16 > rest.
    $candidate = Get-ChildItem -LiteralPath $modelDir -Filter "mmproj*.gguf" -File -ErrorAction SilentlyContinue |
        Sort-Object @{ Expression = {
            if ($_.Name -match 'bf16') { 1 }
            elseif ($_.Name -match 'f16') { 0 }
            else { 2 }
        } }, Name |
        Select-Object -First 1
    if ($candidate) {
        return $candidate.FullName
    }
    return ""
}

$ResolvedMmprojPath = Resolve-MmprojPath -ExplicitPath $MmprojPath -ModelFilePath $ModelPath
$UseMmproj = [bool]$ResolvedMmprojPath
if (-not $UseMmproj) {
    Write-Warning "No vision projector (mmproj*.gguf) found next to the model."
    Write-Warning "llama-server will start in TEXT-ONLY mode; image recognition will be disabled."
    Write-Warning "Download an mmproj GGUF into the model folder, or pass -MmprojPath."
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

try {
    $models = Invoke-RestMethod -Uri "$BaseUrl/models" -TimeoutSec 2
    $expectedProcesses = @(Get-ExpectedGemmaServerProcess)
    if ($expectedProcesses.Count -gt 0) {
        # If we now have a vision projector but the running server was started
        # text-only (no --mmproj), restart it so image recognition is enabled.
        $runningWithoutVision = @($expectedProcesses | Where-Object { $_.CommandLine -notlike "*--mmproj*" })
        if ($UseMmproj -and $runningWithoutVision.Count -gt 0) {
            foreach ($staleProcess in $expectedProcesses) {
                Stop-Process -Id $staleProcess.ProcessId -Force
                Write-Host "Stopped text-only Gemma llama-server pid=$($staleProcess.ProcessId) to enable vision (mmproj)"
            }
            Start-Sleep -Seconds 2
        } else {
            Write-Host "Expected Gemma llama-server is already running at $BaseUrl"
            $models | ConvertTo-Json -Depth 8
            exit 0
        }
    } else {
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
    }
} catch {
    if ($_.Exception.Message -like "Port ${Port} is already in use*") {
        throw
    }
    # No server is ready yet. Continue and start llama-server.
}

$Arguments = @(
    "-m", $ModelPath
)

if ($UseMmproj) {
    $Arguments += @("--mmproj", $ResolvedMmprojPath)
}

$Arguments += @(
    "--alias", $Alias,
    "--host", $HostAddress,
    "--port", [string]$Port,
    "--ctx-size", [string]$ContextSize,
    "--parallel", "1",
    "--reasoning", $Reasoning,
    "--reasoning-budget", [string]$ReasoningBudget,
    "--reasoning-format", $ReasoningFormat,
    "--cache-type-k", $CacheTypeK,
    "--cache-type-v", $CacheTypeV
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
if ($UseMmproj) {
    Write-Host "Vision (mmproj): $ResolvedMmprojPath"
} else {
    Write-Host "Vision (mmproj): DISABLED (text-only mode)"
}
Write-Host "Context size: $ContextSize"
Write-Host "KV cache: K=$CacheTypeK V=$CacheTypeV"
Write-Host "Logs: $StdOutLog"
Write-Host "Errors: $StdErrLog"
