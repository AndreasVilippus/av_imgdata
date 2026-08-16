param(
  [string]$ConfigPath = "",
  [string]$WorkerBin = "",
  [string]$PathBaseDir = "",
  [string]$ApiUrl = "",
  [string]$EnrollmentCode = "",
  [switch]$InsecureTls
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
$InitializeScript = Join-Path $BundleRoot "Initialize-AVImgDataWorker.ps1"
if (-not (Test-Path -LiteralPath $InitializeScript)) {
  $InitializeScript = Join-Path $PSScriptRoot "Initialize-AVImgDataWorker.ps1"
}

foreach ($required in @($ApiLoop, $WorkerBin, $ConfigPath, $InitializeScript)) {
  if (-not (Test-Path -LiteralPath $required)) {
    throw "Required worker file is missing: $required"
  }
}

$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
if (-not $PathBaseDir.Trim()) { $PathBaseDir = [string]$config.path_base_dir }
if (-not $ApiUrl.Trim()) { $ApiUrl = [string]$config.worker_api_base_url }
$WorkerId = [string]$config.worker_id
$ModelPack = [string]$config.processors.face.model_name
if (-not $ModelPack.Trim()) { $ModelPack = "buffalo_l" }

if (-not $PathBaseDir.Trim()) { throw "PathBaseDir is missing in arguments and configuration." }
if (-not $ApiUrl.Trim()) { throw "ApiUrl is missing in arguments and configuration." }
if (-not $WorkerId.Trim()) { throw "worker_id is missing in configuration." }

if (-not (Test-Path -LiteralPath $PathBaseDir)) {
  throw "Worker path base is not accessible: $PathBaseDir"
}

if (-not (Test-Path -LiteralPath $TokenPath) -and -not $EnrollmentCode.Trim()) {
  $EnrollmentCode = Read-Host "Worker token not found. Enter registration code"
}

Write-Host "Synchronizing worker configuration and DSM-authorized model files."
$initializeArgs = @{
  ApiUrl = $ApiUrl
  WorkerId = $WorkerId
  PathBaseDir = $PathBaseDir
  ModelPack = $ModelPack
  ConfigPath = $ConfigPath
}
if ($EnrollmentCode.Trim()) {
  $initializeArgs.EnrollmentCode = $EnrollmentCode
}
if ($InsecureTls) {
  $initializeArgs.InsecureTls = $true
}
& $InitializeScript @initializeArgs
if ($LASTEXITCODE -ne 0) {
  throw "Worker initialization/model synchronization failed with code $LASTEXITCODE"
}

Write-Host "Starting AV ImgData worker in continuous foreground mode."
Write-Host "Bundle:    $BundleRoot"
Write-Host "Config:    $ConfigPath"
Write-Host "API URL:   $ApiUrl"
Write-Host "Path base: $PathBaseDir"
Write-Host "Models:    synchronized from DSM authority"
if ($InsecureTls) {
  Write-Warning "TLS certificate verification is disabled for Worker API requests."
}
Write-Host "Stop with Ctrl+C."

Push-Location $BundleRoot
try {
  $loopArgs = @(
    "--config", $ConfigPath,
    "--worker-bin", $WorkerBin,
    "--api-url", $ApiUrl,
    "--path-base-dir", $PathBaseDir
  )
  if ($InsecureTls) {
    $loopArgs += @("--insecure-tls")
  }

  & $ApiLoop @loopArgs

  $exitCode = $LASTEXITCODE
} finally {
  Pop-Location
}

if ($exitCode -ne 0) {
  throw "Worker API loop exited with code $exitCode"
}
