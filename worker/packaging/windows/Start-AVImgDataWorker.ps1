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
  $ConfigPath = Join-Path $BundleRoot "config\worker-config.json"
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
$ConfigureExe = Join-Path $BundleRoot "bin\av-imgdata-worker-configure.exe"
$TokenPath = Join-Path $BundleRoot "worker.token"
$HashManifest = Join-Path $BundleRoot "SHA256SUMS.txt"
$InitializeScript = Join-Path $BundleRoot "Initialize-AVImgDataWorker.ps1"
if (-not (Test-Path -LiteralPath $InitializeScript)) {
  $InitializeScript = Join-Path $PSScriptRoot "Initialize-AVImgDataWorker.ps1"
}

foreach ($required in @($ApiLoop, $WorkerBin, $ConfigureExe, $InitializeScript)) {
  if (-not (Test-Path -LiteralPath $required)) {
    throw "Required worker file is missing: $required"
  }
}

function Get-BundleRelativePath {
  param([string]$Path)

  $fullPath = [System.IO.Path]::GetFullPath($Path)
  $rootPath = [System.IO.Path]::GetFullPath($BundleRoot).TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
  if ($fullPath.StartsWith($rootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
    return $fullPath.Substring($rootPath.Length).Replace("\", "/")
  }
  return ""
}

function Get-ExpectedBundleHash {
  param([string]$Path)

  if (-not (Test-Path -LiteralPath $HashManifest)) {
    return ""
  }
  $relativePath = Get-BundleRelativePath -Path $Path
  if (-not $relativePath.Trim()) {
    return ""
  }
  foreach ($line in Get-Content -LiteralPath $HashManifest) {
    $trimmed = [string]$line
    $trimmed = $trimmed.Trim()
    if (-not $trimmed) {
      continue
    }
    $parts = $trimmed -split "\s+", 2
    if ($parts.Count -ne 2) {
      continue
    }
    $hash = $parts[0].TrimStart("\").ToLowerInvariant()
    $entryPath = $parts[1].Trim().TrimStart("*").TrimStart(".", "/", "\").Replace("\", "/")
    if ($entryPath -ieq $relativePath) {
      return $hash
    }
  }
  return ""
}

function Assert-BundleFileHash {
  param([string]$Path)

  $expected = Get-ExpectedBundleHash -Path $Path
  if (-not $expected.Trim()) {
    return
  }
  $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne $expected) {
    throw "Worker file hash mismatch: $Path`nExpected: $expected`nActual:   $actual"
  }
}

function Write-WorkerExecutionDiagnostics {
  param(
    [string]$Path,
    [System.Management.Automation.ErrorRecord]$ErrorRecord
  )

  Write-Warning "Windows blocked or failed to start the worker executable: $Path"
  if (Test-Path -LiteralPath $Path) {
    try {
      $hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
      Write-Warning "SHA256: $hash"
    } catch {
      Write-Warning "SHA256 could not be read: $($_.Exception.Message)"
    }
  } else {
    Write-Warning "The file no longer exists. Windows Security may have quarantined it."
  }
  Write-Warning "Original error: $($ErrorRecord.Exception.Message)"
  Write-Warning "If SHA256SUMS.txt is present and the hash check above did not fail, report this exact executable to Microsoft Security Intelligence as a false positive or allow only this exact file after verifying the hash."
}

Assert-BundleFileHash -Path $ApiLoop
Assert-BundleFileHash -Path $WorkerBin

function Read-WorkerPrompt {
  param(
    [Parameter(Mandatory=$true)][string]$Label,
    [string]$Default = "",
    [switch]$Required
  )

  while ($true) {
    if ($Default.Trim()) {
      $value = Read-Host "$Label [$Default]"
      if (-not $value.Trim()) { $value = $Default }
    } else {
      $value = Read-Host $Label
    }
    $value = [string]$value
    if ($value.Trim() -or -not $Required) { return $value.Trim() }
    Write-Host "This value is required."
  }
}

function Read-WorkerJsonString {
  param([Parameter(Mandatory=$true)][string]$Path, [Parameter(Mandatory=$true)][string]$Name)

  if (-not (Test-Path -LiteralPath $Path)) { return "" }
  try {
    $json = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $value = $json
    foreach ($part in $Name.Split(".")) {
      if ($null -eq $value) { return "" }
      $value = $value.$part
    }
    return [string]$value
  } catch {
    return ""
  }
}

function New-WorkerConfigIfMissing {
  if (Test-Path -LiteralPath $ConfigPath) { return }

  $ExampleConfigPath = Join-Path $BundleRoot "config\worker-config.example.json"
  Write-Host "Worker configuration was not found and will be created:"
  Write-Host "  $ConfigPath"
  if (Test-Path -LiteralPath $ExampleConfigPath) {
    Write-Host ""
    Write-Host "Example configuration values:"
    Write-Host "  worker_id:           $(Read-WorkerJsonString -Path $ExampleConfigPath -Name "worker_id")"
    Write-Host "  worker_api_base_url: $(Read-WorkerJsonString -Path $ExampleConfigPath -Name "worker_api_base_url")"
    Write-Host "  path_base_dir:       $(Read-WorkerJsonString -Path $ExampleConfigPath -Name "path_base_dir")"
    Write-Host "  log_level:           off (alternatives: error, warning, info, debug)"
    Write-Host ""
  }

  $defaultWorkerId = Read-WorkerJsonString -Path $ExampleConfigPath -Name "worker_id"
  if (-not $defaultWorkerId.Trim()) { $defaultWorkerId = "worker-01" }
  $createdWorkerId = Read-WorkerPrompt -Label "Worker ID" -Default $defaultWorkerId -Required
  $createdApiUrl = Read-WorkerPrompt -Label "Worker API base URL, for example https://nas:5001/worker-api" -Default $ApiUrl -Required
  $defaultPathBaseDir = $PathBaseDir
  if (-not $defaultPathBaseDir.Trim()) { $defaultPathBaseDir = Read-WorkerJsonString -Path $ExampleConfigPath -Name "path_base_dir" }
  $createdPathBaseDir = Read-WorkerPrompt -Label "Shared Photos path base, for example \\nas\photo" -Default $defaultPathBaseDir -Required
  Write-Host "Log level defaults to off. Alternatives: error, warning, info, debug."
  $createdLogLevel = Read-WorkerPrompt -Label "Log level" -Default "off"
  if (@("off", "error", "warning", "info", "debug") -notcontains $createdLogLevel) {
    throw "Invalid log level: $createdLogLevel"
  }
  $createdModelPack = Read-WorkerPrompt -Label "Face model pack" -Default "buffalo_l" -Required

  & $ConfigureExe `
    --config $ConfigPath `
    --worker-id $createdWorkerId `
    --api-url $createdApiUrl `
    --path-base-dir $createdPathBaseDir `
    --model-pack $createdModelPack `
    --log-level $createdLogLevel
  if ($LASTEXITCODE -ne 0) {
    throw "Worker configuration creation failed with code $LASTEXITCODE"
  }
}

New-WorkerConfigIfMissing
if (-not (Test-Path -LiteralPath $ConfigPath)) {
  throw "Required worker file is missing: $ConfigPath"
}

$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
if (-not $PathBaseDir.Trim()) { $PathBaseDir = [string]$config.path_base_dir }
if (-not $ApiUrl.Trim()) { $ApiUrl = [string]$config.worker_api_base_url }
$WorkerId = [string]$config.worker_id
$ModelPack = [string]$config.processors.face.model_name
if (-not $ModelPack.Trim()) { $ModelPack = "buffalo_l" }
$LogLevel = [string]$config.log_level
if (-not $LogLevel.Trim()) { $LogLevel = "off" }

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
  LogLevel = $LogLevel
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

  try {
    & $ApiLoop @loopArgs
  } catch {
    Write-WorkerExecutionDiagnostics -Path $ApiLoop -ErrorRecord $_
    throw
  }

  $exitCode = $LASTEXITCODE
} finally {
  Pop-Location
}

if ($exitCode -ne 0) {
  throw "Worker API loop exited with code $exitCode"
}
