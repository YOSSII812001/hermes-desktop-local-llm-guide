param(
    [Parameter(Mandatory = $true)]
    [string]$Query,

    [Parameter(Mandatory = $false)]
    [string]$Workdir = $env:USERPROFILE,

    [Parameter(Mandatory = $false)]
    [int]$MaxRounds = 6,

    [Parameter(Mandatory = $false)]
    [int]$RoundTimeout = 900,

    [Parameter(Mandatory = $false)]
    [switch]$ReplaceActive,

    [Parameter(Mandatory = $false)]
    [switch]$DryRun
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

try {
    [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {
    # Best effort for Windows PowerShell compatibility.
}

if ([string]::IsNullOrWhiteSpace($Query)) {
    throw "Query is required."
}

$runner = Join-Path $env:LOCALAPPDATA "hermes\scripts\codex_autonomous_runner.py"
$xResearch = Join-Path $env:LOCALAPPDATA "hermes\scripts\x_research.py"

if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw "codex_autonomous_runner.py not found: $runner"
}
if (-not (Test-Path -LiteralPath $xResearch -PathType Leaf)) {
    throw "x_research.py not found: $xResearch"
}

$promptLines = @(
    "Research the following topic on X and produce a concise report.",
    "",
    "Topic:",
    $Query,
    "Process:",
    "1. First run this Hermes helper to execute multiple X searches.",
    "   py $xResearch TOPIC --max-queries 4 --pretty",
    "2. Inspect research_summary, unique_citations, and degraded_queries.",
    "3. If citations are sparse or degraded is high, adjust search terms and run the helper again.",
    "4. In the final report, summarize latest trends, evidence links, caveats, and useful follow-up queries.",
    "5. Do not print secrets, credentials, or long logs."
)
$prompt = $promptLines -join " "

$runnerArgs = @(
    $runner,
    "--start-and-dispatch",
    $prompt,
    "--workdir",
    $Workdir,
    "--max-rounds",
    [string]$MaxRounds,
    "--round-timeout",
    [string]$RoundTimeout
)

if ($ReplaceActive) {
    $runnerArgs += "--replace-active"
}
if ($DryRun) {
    $runnerArgs += "--dry-run"
    $runnerArgs += "--json"
}

& py @runnerArgs
exit $LASTEXITCODE
