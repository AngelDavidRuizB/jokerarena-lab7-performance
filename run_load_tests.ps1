param(
    [string]$TargetUrl = "http://localhost:18080/api/leaderboard/top?limit=20",
    [string]$WebUrl = "http://localhost:13000/leaderboard",
    [string]$Duration = "30s"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Resolve-K6 {
    $cmd = Get-Command k6 -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "C:\Program Files\k6\k6.exe",
        "$env:LOCALAPPDATA\Programs\k6\k6.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    throw "k6 executable not found. Install GrafanaLabs.k6 or add k6 to PATH."
}

$k6 = Resolve-K6
Write-Host "Using k6: $k6"
& $k6 version

New-Item -ItemType Directory -Force -Path "results" | Out-Null

Write-Host "`n=== 1. Smoke check (API Gateway + Web SSR) ==="
$gwResp = Invoke-WebRequest -Uri $TargetUrl -UseBasicParsing -TimeoutSec 10
if ($gwResp.StatusCode -ne 200) { throw "Gateway returned $($gwResp.StatusCode)" }
$webResp = Invoke-WebRequest -Uri $WebUrl -UseBasicParsing -TimeoutSec 10
if ($webResp.StatusCode -ne 200) { throw "Web SSR returned $($webResp.StatusCode)" }
Write-Host "Gateway (200) and Web SSR (200) healthy."

$levels = @(1, 50, 200, 500, 2000)
foreach ($vus in $levels) {
    Write-Host "`n=== 2. Running fixed load level: $vus VUs ($Duration) ==="
    $summaryPath = "results/summary_${vus}vu.json"
    $logPath = "results/k6_${vus}vu.txt"
    $env:TARGET_URL = $TargetUrl
    $env:K6_MODE = "fixed"
    $env:K6_VUS = "$vus"
    $env:K6_DURATION = $Duration

    & $k6 run --summary-export $summaryPath "k6/performance_test.js" | Tee-Object -FilePath $logPath
    Start-Sleep -Seconds 5
}

Write-Host "`n=== 3. Running unified stages sweep (1 -> 50 -> 200 -> 500 -> 2000 -> 0) ==="
$env:TARGET_URL = $TargetUrl
$env:K6_MODE = "stages"
& $k6 run --summary-export "results/summary_stages.json" --out "csv=results/stages_metrics.csv" "k6/performance_test.js" | Tee-Object -FilePath "results/k6_stages.txt"

Write-Host "`n=== Done. Run 'python analyze_results.py' to build the performance curve and knee analysis. ==="
