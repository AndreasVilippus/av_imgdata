param(
  [Parameter(Mandatory=$true)][string]$ApiUrl,
  [string]$EnrollmentCode = "",
  [Parameter(Mandatory=$true)][string]$WorkerId,
  [Parameter(Mandatory=$true)][string]$PathBaseDir,
  [string]$ModelPack = "buffalo_l",
  [string]$ConfigPath = "",
  [switch]$ForceEnroll
)

$ErrorActionPreference = "Stop"
$ApiUrl = $ApiUrl.TrimEnd('/')
$RootCandidate = [System.IO.Path]::GetFullPath($PSScriptRoot)
if (-not (Test-Path -LiteralPath (Join-Path $RootCandidate "bin"))) {
  $RootCandidate = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
}
$BundleRoot = $RootCandidate
if (-not $ConfigPath.Trim()) {
  $ConfigPath = Join-Path $BundleRoot "config\worker-config.example.json"
}
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
$TokenPath = Join-Path $BundleRoot "worker.token"
$ModelRoot = Join-Path $BundleRoot ".models\face"
$ConfigureExe = Join-Path $BundleRoot "bin\av-imgdata-worker-configure.exe"
$ModelSyncExe = Join-Path $BundleRoot "bin\av-imgdata-worker-model-sync.exe"

function Protect-WorkerTokenFile {
  param([Parameter(Mandatory=$true)][string]$Path)
  try {
    $currentIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $Path "/inheritance:r" "/grant:r" "${currentIdentity}:(R,W)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls exited with code $LASTEXITCODE" }
  } catch {
    Write-Warning "The worker token was saved, but its ACL could not be restricted automatically: $($_.Exception.Message)"
  }
}

function Get-WorkerApiErrorDetail {
  param([Parameter(Mandatory=$true)]$ErrorRecord)
  $parts = New-Object System.Collections.Generic.List[string]
  if ($ErrorRecord.ErrorDetails -and $ErrorRecord.ErrorDetails.Message) {
    $parts.Add([string]$ErrorRecord.ErrorDetails.Message)
  }
  $response = $ErrorRecord.Exception.Response
  if ($response) {
    try {
      $parts.Add(("HTTP {0} {1}" -f [int]$response.StatusCode, [string]$response.StatusDescription).Trim())
    } catch { }
    try {
      $stream = $response.GetResponseStream()
      if ($stream) {
        $reader = New-Object System.IO.StreamReader($stream)
        $body = $reader.ReadToEnd()
        $reader.Dispose()
        if ($body) { $parts.Add($body) }
      }
    } catch { }
  }
  if ($parts.Count -eq 0) { $parts.Add([string]$ErrorRecord.Exception.Message) }
  return ($parts | Select-Object -Unique) -join " | "
}

foreach ($required in @($ConfigureExe, $ModelSyncExe)) {
  if (-not (Test-Path -LiteralPath $required)) {
    throw "Required worker tool is missing: $required"
  }
}

$token = ""
if ((Test-Path -LiteralPath $TokenPath) -and -not $ForceEnroll) {
  $token = ([System.IO.File]::ReadAllText($TokenPath)).Trim()
  if ($token) { Write-Host "Using existing worker token from $TokenPath" }
}

if (-not $token) {
  if (-not $EnrollmentCode.Trim()) {
    throw "EnrollmentCode is required because no reusable worker.token exists."
  }
  Write-Host "Enrolling worker '$WorkerId' against $ApiUrl"
  try {
    $enrollment = Invoke-RestMethod -Method Post -Uri "$ApiUrl/enroll" -ContentType "application/json" -Body (@{
      enrollment_code = $EnrollmentCode
      worker_id = $WorkerId
    } | ConvertTo-Json)
  } catch {
    throw "Worker enrollment failed: $(Get-WorkerApiErrorDetail -ErrorRecord $_)"
  }
  if (-not $enrollment.token) { throw "Enrollment response did not contain a token." }
  $token = [string]$enrollment.token
  [System.IO.File]::WriteAllText($TokenPath, $token, [System.Text.UTF8Encoding]::new($false))
}

Protect-WorkerTokenFile -Path $TokenPath

& $ConfigureExe `
  --config $ConfigPath `
  --worker-id $WorkerId `
  --api-url $ApiUrl `
  --path-base-dir $PathBaseDir `
  --model-pack $ModelPack
if ($LASTEXITCODE -ne 0) {
  throw "Worker configuration failed with exit code $LASTEXITCODE"
}

& $ModelSyncExe `
  --api-url $ApiUrl `
  --token-file $TokenPath `
  --worker-id $WorkerId `
  --model-root $ModelRoot `
  --model-pack $ModelPack
if ($LASTEXITCODE -ne 0) {
  throw "Worker token and configuration were saved, but model synchronization failed with exit code $LASTEXITCODE. Rerun this command after resolving the NAS-side condition; the existing worker.token will be reused."
}

Write-Host "Worker enrolled, configured and model files synchronized."
Write-Host "Config: $ConfigPath"
Write-Host "Token:  $TokenPath"
Write-Host "Models: $(Join-Path $ModelRoot $ModelPack)"
