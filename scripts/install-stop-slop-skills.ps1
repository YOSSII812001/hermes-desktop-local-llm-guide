[CmdletBinding()]
param(
  [string]$SourceUrl = "https://github.com/hardikpandya/stop-slop.git",
  [string]$SourceDir = (Join-Path $env:LOCALAPPDATA "hermes\skill-sources\stop-slop"),
  [string[]]$Targets = @(
    (Join-Path $env:USERPROFILE ".claude\skills\stop-slop"),
    (Join-Path $env:USERPROFILE ".codex\skills\stop-slop"),
    (Join-Path $env:USERPROFILE ".agents\skills\stop-slop")
  ),
  [switch]$SkipClaudeDesktopPlugin,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Invoke-Step {
  param(
    [Parameter(Mandatory = $true)][string]$Message,
    [Parameter(Mandatory = $true)][scriptblock]$Action
  )

  if ($DryRun) {
    Write-Host "DRY-RUN: $Message"
    return
  }

  Write-Host $Message
  & $Action
}

function Assert-StopSlopSource {
  param([Parameter(Mandatory = $true)][string]$Path)

  $required = @(
    "SKILL.md",
    "README.md",
    "references\phrases.md",
    "references\structures.md",
    "references\examples.md"
  )

  foreach ($relative in $required) {
    $candidate = Join-Path $Path $relative
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
      throw "stop-slop source is missing required file: $relative"
    }
  }
}

function Get-ClaudeDesktopSkillPluginManifests {
  $pluginBase = Join-Path $env:APPDATA "Claude\local-agent-mode-sessions\skills-plugin"
  if (-not (Test-Path -LiteralPath $pluginBase -PathType Container)) {
    return @()
  }

  return @(
    Get-ChildItem -LiteralPath $pluginBase -Recurse -Filter "manifest.json" |
      Sort-Object LastWriteTime -Descending
  )
}

function Install-ClaudeDesktopSkillPlugin {
  param([Parameter(Mandatory = $true)][string]$Path)

  $manifests = Get-ClaudeDesktopSkillPluginManifests
  if ($manifests.Count -eq 0) {
    Write-Warning "Claude Desktop skills-plugin manifest was not found. Start Claude Desktop local agent mode, then rerun this script if needed."
    return
  }

  foreach ($manifestFile in $manifests) {
    $manifest = $manifestFile.FullName
    $pluginRoot = Split-Path -Parent $manifest
    $target = Join-Path $pluginRoot "skills\stop-slop"

    if (-not $target.StartsWith($pluginRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to write outside Claude Desktop skills-plugin root: $target"
    }

    Invoke-Step "Install stop-slop to Claude Desktop skills-plugin: $target" {
      New-Item -ItemType Directory -Force -Path $target | Out-Null
      Copy-Item -Path (Join-Path $Path "*") -Destination $target -Recurse -Force
    }

    Invoke-Step "Update Claude Desktop skills-plugin manifest: $manifest" {
      $backup = "$manifest.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
      Copy-Item -LiteralPath $manifest -Destination $backup

      $json = Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
      $skills = @($json.skills)
      $existing = $skills |
        Where-Object { $_.name -eq "stop-slop" -or $_.skillId -eq "stop-slop" } |
        Select-Object -First 1

      if ($existing) {
        $existing.enabled = $true
        if ($existing.PSObject.Properties.Name -contains "updatedAt") {
          $existing.updatedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.ffffffZ")
        }
      } else {
        $entry = [pscustomobject]@{
          skillId = "stop-slop"
          name = "stop-slop"
          description = "Remove AI writing patterns from prose. Use when drafting, editing, or reviewing text to eliminate predictable AI tells."
          creatorType = "user"
          updatedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.ffffffZ")
          enabled = $true
        }
        $json.skills = @($skills + $entry)
      }

      if ($json.PSObject.Properties.Name -contains "lastUpdated") {
        $epoch = [datetime]"1970-01-01T00:00:00Z"
        $json.lastUpdated = [int64](((Get-Date).ToUniversalTime()) - $epoch).TotalMilliseconds
      }

      $text = $json | ConvertTo-Json -Depth 64
      [System.IO.File]::WriteAllText($manifest, $text + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
    }
  }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "git command was not found. Install Git or pass an existing -SourceDir."
}

$sourceParent = Split-Path -Parent $SourceDir
Invoke-Step "Ensure source parent exists: $sourceParent" {
  New-Item -ItemType Directory -Force -Path $sourceParent | Out-Null
}

if (Test-Path -LiteralPath (Join-Path $SourceDir ".git") -PathType Container) {
  Invoke-Step "Update stop-slop source: $SourceDir" {
    git -C $SourceDir pull --ff-only
  }
} elseif (Test-Path -LiteralPath $SourceDir) {
  Write-Host "Using existing source directory: $SourceDir"
} else {
  Invoke-Step "Clone stop-slop source into: $SourceDir" {
    git clone $SourceUrl $SourceDir
  }
}

if (-not $DryRun) {
  Assert-StopSlopSource -Path $SourceDir
}

foreach ($target in $Targets) {
  $sourceFull = [System.IO.Path]::GetFullPath($SourceDir).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
  $targetFull = [System.IO.Path]::GetFullPath($target).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
  if ([string]::Equals($sourceFull, $targetFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    Write-Host "Skipping target because it is the source directory: $target"
    continue
  }

  $targetParent = Split-Path -Parent $target
  Invoke-Step "Ensure target parent exists: $targetParent" {
    New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
  }

  Invoke-Step "Install stop-slop to: $target" {
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Path (Join-Path $SourceDir "*") -Destination $target -Recurse -Force
  }
}

if (-not $SkipClaudeDesktopPlugin) {
  Install-ClaudeDesktopSkillPlugin -Path $SourceDir
}

Write-Host "stop-slop skill install complete"
