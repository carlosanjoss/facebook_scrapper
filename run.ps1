[CmdletBinding()]
param(
    [switch]$Login,
    [switch]$Once,
    [switch]$NoComments,
    [switch]$NoExport,
    [ValidateRange(0, [int]::MaxValue)]
    [int]$LimitPages,
    [ValidateRange(0, [int]::MaxValue)]
    [int]$LimitPosts,
    [ValidateRange(0, [int]::MaxValue)]
    [int]$SkipRecentEmptyHours,
    [ValidateRange(0, [int]::MaxValue)]
    [int]$RestartBrowserEveryPosts
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot
$env:PYTHONUTF8 = "1"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Ambiente ainda não preparado; executando setup.ps1..."
    & (Join-Path $ProjectRoot "setup.ps1")
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Ambiente .venv indisponível. Execute .\setup.ps1 e confira o erro exibido."
}

if ($Login) {
    & $VenvPython -m app.browser.login
    exit $LASTEXITCODE
}

$ScraperArgs = @()
if ($Once) { $ScraperArgs += "--once" }
if ($NoComments) { $ScraperArgs += "--no-comments" }
if ($NoExport) { $ScraperArgs += "--no-export" }
if ($PSBoundParameters.ContainsKey("LimitPages")) {
    $ScraperArgs += @("--limit-pages", $LimitPages.ToString())
}
if ($PSBoundParameters.ContainsKey("LimitPosts")) {
    $ScraperArgs += @("--limit-posts", $LimitPosts.ToString())
}
if ($PSBoundParameters.ContainsKey("SkipRecentEmptyHours")) {
    $ScraperArgs += @("--skip-recent-empty-hours", $SkipRecentEmptyHours.ToString())
}
if ($PSBoundParameters.ContainsKey("RestartBrowserEveryPosts")) {
    $ScraperArgs += @("--restart-browser-every-posts", $RestartBrowserEveryPosts.ToString())
}

& $VenvPython -m app.main @ScraperArgs
exit $LASTEXITCODE
