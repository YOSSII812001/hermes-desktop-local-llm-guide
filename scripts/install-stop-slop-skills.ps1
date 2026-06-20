[CmdletBinding()]
param(
  [string]$SourceUrl = "https://github.com/hardikpandya/stop-slop.git",
  [string]$SourceDir = (Join-Path $env:LOCALAPPDATA "hermes\skill-sources\stop-slop"),
  [string[]]$Targets = @(
    (Join-Path $env:USERPROFILE ".claude\skills\stop-slop"),
    (Join-Path $env:USERPROFILE ".codex\skills\stop-slop"),
    (Join-Path $env:USERPROFILE ".agents\skills\stop-slop")
  ),
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
  $targetParent = Split-Path -Parent $target
  Invoke-Step "Ensure target parent exists: $targetParent" {
    New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
  }

  Invoke-Step "Install stop-slop to: $target" {
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Path (Join-Path $SourceDir "*") -Destination $target -Recurse -Force
  }
}

Write-Host "stop-slop skill install complete"
