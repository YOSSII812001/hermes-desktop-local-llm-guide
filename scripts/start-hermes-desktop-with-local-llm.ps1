param(
    [switch]$SelfTest,
    [string]$StartLlamaScript = "$PSScriptRoot\start-gemma-llama-server.ps1",
    [string]$StopLlamaScript = "$PSScriptRoot\stop-gemma-llama-server.ps1",
    [string]$HermesExe = "$env:LOCALAPPDATA\hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe",
    [string]$BaseUrl = "http://127.0.0.1:8080/v1",
    [string]$ExpectedModel = "gemma-4-12b-it",
    [string]$ExpectedServerExePath = "$env:USERPROFILE\tools\llama.cpp-b9498-cuda-12.4\llama-server.exe",
    [string]$ExpectedModelPath = "$env:USERPROFILE\.cache\lm-studio\models\google\gemma-4-12B-it-qat-q4_0-gguf\gemma-4-12b-it-qat-q4_0.gguf",
    [string]$ExpectedProjectorPath = "$env:USERPROFILE\.cache\lm-studio\models\google\gemma-4-12B-it-qat-q4_0-gguf\mmproj-gemma-4-12b-it-qat-q4_0.gguf",
    [string]$LogsDir = "$env:USERPROFILE\.hermes\logs"
)

$ErrorActionPreference = "Stop"

function Resolve-ComparablePath {
    param([string]$Path)

    $fullPath = if (Test-Path -LiteralPath $Path -PathType Leaf) {
        (Resolve-Path -LiteralPath $Path).Path
    } else {
        [System.IO.Path]::GetFullPath($Path)
    }

    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) { return $fullPath }

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
        private static extern uint GetFinalPathNameByHandle(SafeFileHandle handle, StringBuilder path, uint pathLength, uint flags);
        public static string GetFinalPath(string path) {
            using (FileStream stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete)) {
                StringBuilder buffer = new StringBuilder(32768);
                uint length = GetFinalPathNameByHandle(stream.SafeFileHandle, buffer, (uint)buffer.Capacity, 0);
                if (length == 0 || length >= buffer.Capacity) { throw new Win32Exception(Marshal.GetLastWin32Error()); }
                return buffer.ToString();
            }
        }
    }
}
'@
    }

    $finalPath = [Hermes.LocalLlm.NativePath]::GetFinalPath($fullPath)
    if ($finalPath.StartsWith("\\?\UNC\", [StringComparison]::OrdinalIgnoreCase)) { return "\\" + $finalPath.Substring(8) }
    if ($finalPath.StartsWith("\\?\", [StringComparison]::OrdinalIgnoreCase)) { return $finalPath.Substring(4) }
    return $finalPath
}

$ServerExePath = Resolve-ComparablePath $ExpectedServerExePath
$ModelPath = Resolve-ComparablePath $ExpectedModelPath
$ProjectorPath = Resolve-ComparablePath $ExpectedProjectorPath
$BaseUri = [uri]$BaseUrl

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

function Test-ProcessExecutablePath {
    param($Process, [string]$ExpectedPath)

    if ([string]::IsNullOrWhiteSpace($Process.ExecutablePath)) { return $false }
    try {
        return [StringComparer]::OrdinalIgnoreCase.Equals(
            (Resolve-ComparablePath $Process.ExecutablePath), $ExpectedPath)
    } catch {
        return $false
    }
}

function Get-LocalLlmServerProcesses {
    Get-CimInstance Win32_Process -Filter "name = 'llama-server.exe'" |
        Where-Object {
            (Test-ProcessExecutablePath -Process $_ -ExpectedPath $ServerExePath) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "-m" -ExpectedValue $ModelPath -PathValue) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "--mmproj" -ExpectedValue $ProjectorPath -PathValue) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "--alias" -ExpectedValue $ExpectedModel) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "--host" -ExpectedValue $BaseUri.Host) -and
            (Test-CommandLineNamedArgument -CommandLine $_.CommandLine -Name "--port" -ExpectedValue $BaseUri.Port)
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

    & $StopLlamaScript `
        -ServerExe $ServerExePath `
        -ModelPath $ModelPath `
        -MmprojPath $ProjectorPath `
        -Alias $ExpectedModel `
        -HostAddress $BaseUri.Host `
        -Port $BaseUri.Port `
        2>&1 | ForEach-Object {
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
            & $StartLlamaScript `
                -ServerExe $ServerExePath `
                -ModelPath $ModelPath `
                -MmprojPath $ProjectorPath `
                -Alias $ExpectedModel `
                -HostAddress $BaseUri.Host `
                -Port $BaseUri.Port `
                2>&1 | ForEach-Object {
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
