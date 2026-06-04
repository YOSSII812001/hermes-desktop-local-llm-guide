param(
    [string]$Alias = "gemma-4-12b-it"
)

$ErrorActionPreference = "Stop"

$targets = Get-CimInstance Win32_Process -Filter "name = 'llama-server.exe'" |
    Where-Object {
        $_.CommandLine -like "*gemma-4-12*-it-*.gguf*" -and
        $_.CommandLine -like "*--alias*$Alias*"
    }

if (-not $targets) {
    Write-Host "No Gemma llama-server process is running."
    exit 0
}

foreach ($target in $targets) {
    Stop-Process -Id $target.ProcessId -Force
    Write-Host "Stopped llama-server pid=$($target.ProcessId)"
}
