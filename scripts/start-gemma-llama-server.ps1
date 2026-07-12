param(
    [string]$ServerExe = "$env:USERPROFILE\tools\llama.cpp-b9637-cuda-12.4\llama-server.exe",
    [string]$ModelPath = "$env:USERPROFILE\.cache\lm-studio\models\google\gemma-4-12B-it-qat-q4_0-gguf\gemma-4-12b-it-qat-q4_0.gguf",
    [string]$MmprojPath = "",
    [string]$Alias = "gemma-4-12b-it",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8080,
    [ValidateRange(64000, 2147483647)]
    [int]$ContextSize = 65536,
    [ValidateRange(0, 2147483647)]
    [int]$ContextCheckpoints = 0,
    [string]$LogsDir = "$env:USERPROFILE\.hermes\logs",
    [string]$ActionFile = "",
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

if ([string]::IsNullOrWhiteSpace($MmprojPath)) {
    $MmprojPath = Join-Path (Split-Path -Parent $ModelPath) "mmproj-gemma-4-12b-it-qat-q4_0.gguf"
}

function ConvertTo-WindowsCommandLineArgument {
    param([string]$Value)

    if ($Value -match "\s") {
        return '"' + $Value + '"'
    }
    return $Value
}

function Write-ServerAction {
    param([ValidateSet("started", "reused")][string]$Action)

    $line = "HERMES_LLAMA_SERVER_ACTION=$Action"
    Write-Output $line

    if (-not [string]::IsNullOrWhiteSpace($ActionFile)) {
        $fullPath = [System.IO.Path]::GetFullPath($ActionFile)
        $directory = Split-Path -Parent $fullPath
        if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
            New-Item -ItemType Directory -Force -Path $directory | Out-Null
        }
        [System.IO.File]::WriteAllText(
            $fullPath,
            $line,
            [System.Text.UTF8Encoding]::new($false)
        )
    }
}

function Resolve-ComparablePath {
    param([string]$Path)

    $fullPath = if (Test-Path -LiteralPath $Path -PathType Leaf) {
        (Resolve-Path -LiteralPath $Path).Path
    } else {
        [System.IO.Path]::GetFullPath($Path)
    }

    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        return $fullPath
    }

    if (-not ("Hermes.LocalLlm.NativePath" -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace Hermes.LocalLlm {
    public static class NativePath {
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern uint GetFinalPathNameByHandle(
            SafeFileHandle handle, StringBuilder path, uint pathLength, uint flags);

        public static string GetFinalPath(string path) {
            using (FileStream stream = new FileStream(
                path, FileMode.Open, FileAccess.Read,
                FileShare.ReadWrite | FileShare.Delete)) {
                StringBuilder buffer = new StringBuilder(32768);
                uint length = GetFinalPathNameByHandle(
                    stream.SafeFileHandle, buffer, (uint)buffer.Capacity, 0);
                if (length == 0 || length >= buffer.Capacity) {
                    throw new Win32Exception(Marshal.GetLastWin32Error());
                }
                return buffer.ToString();
            }
        }
    }
}
'@
    }

    $finalPath = [Hermes.LocalLlm.NativePath]::GetFinalPath($fullPath)
    if ($finalPath.StartsWith("\\?\UNC\", [StringComparison]::OrdinalIgnoreCase)) {
        return "\\" + $finalPath.Substring(8)
    }
    if ($finalPath.StartsWith("\\?\", [StringComparison]::OrdinalIgnoreCase)) {
        return $finalPath.Substring(4)
    }
    return $finalPath
}

function Test-ProcessExecutablePath {
    param($Process, [string]$ExpectedPath)

    if ([string]::IsNullOrWhiteSpace($Process.ExecutablePath)) {
        return $false
    }

    try {
        $actualPath = Resolve-ComparablePath $Process.ExecutablePath
        return [StringComparer]::OrdinalIgnoreCase.Equals($actualPath, $ExpectedPath)
    } catch {
        return $false
    }
}

function Test-CommandLineNamedArgument {
    param(
        [string]$CommandLine,
        [string]$Name,
        [string]$ExpectedValue,
        [switch]$PathValue
    )

    if ([string]::IsNullOrWhiteSpace($CommandLine)) {
        return $false
    }

    $pattern = "(?i)(?<!\S)$([regex]::Escape($Name))(?:\s+|=)(?:""([^""]*)""|'([^']*)'|([^\s]+))(?=\s|$)"
    $matches = [regex]::Matches($CommandLine, $pattern)
    if ($matches.Count -ne 1) {
        return $false
    }

    $match = $matches[0]
    $actualValue = if ($match.Groups[1].Success) {
        $match.Groups[1].Value
    } elseif ($match.Groups[2].Success) {
        $match.Groups[2].Value
    } else {
        $match.Groups[3].Value
    }

    if ($PathValue) {
        try {
            $actualValue = Resolve-ComparablePath $actualValue
        } catch {
            return $false
        }
    }

    return [StringComparer]::OrdinalIgnoreCase.Equals($actualValue, $ExpectedValue)
}

function Get-ExpectedGemmaServerProcess {
    Get-CimInstance Win32_Process -Filter "name = 'llama-server.exe'" |
        Where-Object {
            (Test-ProcessExecutablePath -Process $_ -ExpectedPath $ServerExe) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "-m" -ExpectedValue $ModelPath -PathValue) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "--alias" -ExpectedValue $Alias) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "--host" -ExpectedValue $HostAddress) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "--port" -ExpectedValue ([string]$Port)) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "--mmproj" -ExpectedValue $MmprojPath -PathValue) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "--ctx-size" -ExpectedValue ([string]$ContextSize)) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "--ctx-checkpoints" -ExpectedValue ([string]$ContextCheckpoints))
        }
}

function Get-AnyGemmaServerProcess {
    Get-CimInstance Win32_Process -Filter "name = 'llama-server.exe'" |
        Where-Object {
            (Test-ProcessExecutablePath -Process $_ -ExpectedPath $ServerExe) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "-m" -ExpectedValue $ModelPath -PathValue) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "--alias" -ExpectedValue $Alias) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "--host" -ExpectedValue $HostAddress) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "--port" -ExpectedValue ([string]$Port))
        }
}

if (-not (Test-Path -LiteralPath $ServerExe -PathType Leaf)) {
    throw "llama-server.exe was not found: $ServerExe"
}

if (-not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) {
    throw "Model file was not found: $ModelPath"
}

if (-not (Test-Path -LiteralPath $MmprojPath -PathType Leaf)) {
    throw "mmproj file was not found: $MmprojPath"
}

$ServerExe = Resolve-ComparablePath $ServerExe
$ModelPath = Resolve-ComparablePath $ModelPath
$MmprojPath = Resolve-ComparablePath $MmprojPath

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

$expectedProcesses = @(Get-ExpectedGemmaServerProcess)
if ($expectedProcesses.Count -gt 0) {
    Write-ServerAction -Action "reused"
    Write-Host "Expected Gemma llama-server is already running at $BaseUrl"
    try {
        $models = Invoke-RestMethod -Uri "$BaseUrl/models" -TimeoutSec 2
        $models | ConvertTo-Json -Depth 8
    } catch {
        Write-Host "Gemma llama-server is still loading; reusing the existing process."
    }
    exit 0
}

$oldGemmaProcesses = @(Get-AnyGemmaServerProcess)
if ($oldGemmaProcesses.Count -gt 0) {
    foreach ($oldProcess in $oldGemmaProcesses) {
        Stop-Process -Id $oldProcess.ProcessId -Force
        Write-Host "Stopped older Gemma llama-server pid=$($oldProcess.ProcessId)"
    }
    Start-Sleep -Seconds 2
}

try {
    $models = Invoke-RestMethod -Uri "$BaseUrl/models" -TimeoutSec 2
    throw "Port ${Port} is already in use by a non-Gemma server at $BaseUrl"
} catch {
    if ($_.Exception.Message -like "Port ${Port} is already in use*") {
        throw
    }
    if ($null -ne $_.Exception.Response) {
        throw "Port ${Port} is already in use by a non-Gemma server at $BaseUrl"
    }
    # No server is ready yet. Continue and start llama-server.
}

$Arguments = @(
    "-m", (ConvertTo-WindowsCommandLineArgument $ModelPath),
    "--alias", $Alias,
    "--host", $HostAddress,
    "--port", [string]$Port,
    "--ctx-size", [string]$ContextSize,
    "--parallel", "1",
    "--ctx-checkpoints", [string]$ContextCheckpoints,
    "--reasoning", $Reasoning,
    "--reasoning-budget", [string]$ReasoningBudget,
    "--reasoning-format", $ReasoningFormat,
    "--cache-type-k", $CacheTypeK,
    "--cache-type-v", $CacheTypeV,
    "--mmproj", (ConvertTo-WindowsCommandLineArgument $MmprojPath)
)

$process = Start-Process `
    -FilePath $ServerExe `
    -ArgumentList $Arguments `
    -WorkingDirectory (Split-Path -Parent $ServerExe) `
    -RedirectStandardOutput $StdOutLog `
    -RedirectStandardError $StdErrLog `
    -WindowStyle Hidden `
    -PassThru

Write-ServerAction -Action "started"
Write-Host "Started llama-server pid=$($process.Id)"
Write-Host "Endpoint: $BaseUrl"
Write-Host "Model alias: $Alias"
Write-Host "Model file: $ModelPath"
Write-Host "Projector file: $MmprojPath"
Write-Host "Context size: $ContextSize"
Write-Host "Context checkpoints: $ContextCheckpoints"
Write-Host "KV cache: K=$CacheTypeK V=$CacheTypeV"
Write-Host "Logs: $StdOutLog"
Write-Host "Errors: $StdErrLog"
