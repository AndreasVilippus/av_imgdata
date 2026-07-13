param(
  [string]$ConfigPath = "",
  [string]$WorkerBin = "",
  [string]$PathBaseDir = "",
  [string]$ApiUrl = ""
)

$ErrorActionPreference = "Stop"

$RootCandidate = [System.IO.Path]::GetFullPath($PSScriptRoot)
if (-not (Test-Path -LiteralPath (Join-Path $RootCandidate "bin"))) {
  $RootCandidate = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
}
$BundleRoot = $RootCandidate

if (-not $ConfigPath.Trim()) {
  $ConfigPath = Join-Path $BundleRoot "config\worker-config.example.json"
} elseif (-not [System.IO.Path]::IsPathRooted($ConfigPath)) {
  $ConfigPath = Join-Path $BundleRoot $ConfigPath
}
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)

if (-not $WorkerBin.Trim()) {
  $WorkerBin = Join-Path $BundleRoot "bin\av-imgdata-worker.exe"
} elseif (-not [System.IO.Path]::IsPathRooted($WorkerBin)) {
  $WorkerBin = Join-Path $BundleRoot $WorkerBin
}
$WorkerBin = [System.IO.Path]::GetFullPath($WorkerBin)

$ApiLoop = Join-Path $BundleRoot "bin\av-imgdata-worker-api-loop.exe"
$TokenPath = Join-Path $BundleRoot "worker.token"

foreach ($required in @($ApiLoop, $WorkerBin, $ConfigPath, $TokenPath)) {
  if (-not (Test-Path -LiteralPath $required)) {
    throw "Required worker file is missing: $required"
  }
}

$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
if (-not $PathBaseDir.Trim()) { $PathBaseDir = [string]$config.path_base_dir }
if (-not $ApiUrl.Trim()) { $ApiUrl = [string]$config.worker_api_base_url }

if (-not $PathBaseDir.Trim()) { throw "PathBaseDir is missing in arguments and configuration." }
if (-not $ApiUrl.Trim()) { throw "ApiUrl is missing in arguments and configuration." }

if (-not (Test-Path -LiteralPath $PathBaseDir)) {
  throw "Worker path base is not accessible: $PathBaseDir"
}

Write-Host "Starting AV ImgData worker in continuous foreground mode."
Write-Host "Bundle:    $BundleRoot"
Write-Host "Config:    $ConfigPath"
Write-Host "API URL:   $ApiUrl"
Write-Host "Path base: $PathBaseDir"
Write-Host "Stop with Ctrl+C."

Push-Location $BundleRoot
try {
  & $ApiLoop `
    --config $ConfigPath `
    --worker-bin $WorkerBin `
    --api-url $ApiUrl `
    --path-base-dir $PathBaseDir

  $exitCode = $LASTEXITCODE
} finally {
  Pop-Location
}

if ($exitCode -ne 0) {
  throw "Worker API loop exited with code $exitCode"
}
