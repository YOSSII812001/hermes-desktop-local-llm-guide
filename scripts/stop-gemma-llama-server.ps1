param(
    [string]$ServerExe = "$env:USERPROFILE\tools\llama.cpp-b9637-cuda-12.4\llama-server.exe",
    [string]$ModelPath = "$env:USERPROFILE\.cache\lm-studio\models\google\gemma-4-12B-it-qat-q4_0-gguf\gemma-4-12b-it-qat-q4_0.gguf",
    [string]$MmprojPath = "$env:USERPROFILE\.cache\lm-studio\models\google\gemma-4-12B-it-qat-q4_0-gguf\mmproj-gemma-4-12b-it-qat-q4_0.gguf",
    [string]$Alias = "gemma-4-12b-it",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"

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

function Test-CommandLineNamedArgument {
    param(
        [Parameter(Mandatory)]
        [string]$CommandLine,
        [Parameter(Mandatory)]
        [string]$Name,
        [Parameter(Mandatory)]
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

$ServerExe = Resolve-ComparablePath $ServerExe
$ModelPath = Resolve-ComparablePath $ModelPath
$MmprojPath = Resolve-ComparablePath $MmprojPath

$targets = Get-CimInstance Win32_Process -Filter "name = 'llama-server.exe'" |
    Where-Object {
        $commandLine = $_.CommandLine
        $commandLine -and
        (Test-ProcessExecutablePath -Process $_ -ExpectedPath $ServerExe) -and
        (Test-CommandLineNamedArgument -CommandLine $commandLine -Name "-m" -ExpectedValue $ModelPath -PathValue) -and
        (Test-CommandLineNamedArgument -CommandLine $commandLine -Name "--mmproj" -ExpectedValue $MmprojPath -PathValue) -and
        (Test-CommandLineNamedArgument -CommandLine $commandLine -Name "--alias" -ExpectedValue $Alias) -and
        (Test-CommandLineNamedArgument -CommandLine $commandLine -Name "--host" -ExpectedValue $HostAddress) -and
        (Test-CommandLineNamedArgument -CommandLine $commandLine -Name "--port" -ExpectedValue ([string]$Port))
    }

if (-not $targets) {
    Write-Host "No matching llama-server process is running."
    exit 0
}

foreach ($target in $targets) {
    Stop-Process -Id $target.ProcessId -Force
    Write-Host "Stopped llama-server pid=$($target.ProcessId)"
}
