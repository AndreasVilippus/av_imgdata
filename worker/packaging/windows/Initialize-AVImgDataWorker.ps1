param(
  [Parameter(Mandatory=$true)][string]$ApiUrl,
  [string]$EnrollmentCode = "",
  [Parameter(Mandatory=$true)][string]$WorkerId,
  [Parameter(Mandatory=$true)][string]$PathBaseDir,
  [string]$ModelPack = "buffalo_l",
  [string]$ConfigPath = "$PSScriptRoot\..\..\config\worker-config.example.json",
  [switch]$ForceEnroll
)

$ErrorActionPreference = "Stop"
$ApiUrl = $ApiUrl.TrimEnd('/')
$BundleRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
$TokenPath = Join-Path $BundleRoot "worker.token"
$ModelRoot = Join-Path $BundleRoot ".models\face"
$ModelDir = Join-Path $ModelRoot $ModelPack

function Protect-WorkerTokenFile {
  param([Parameter(Mandatory=$true)][string]$Path)

  try {
    $currentIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $Path "/inheritance:r" "/grant:r" "${currentIdentity}:(R,W)" | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "icacls exited with code $LASTEXITCODE"
    }
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
      $statusCode = [int]$response.StatusCode
      $statusDescription = [string]$response.StatusDescription
      $parts.Add("HTTP $statusCode $statusDescription".Trim())
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

  if ($parts.Count -eq 0) {
    $parts.Add([string]$ErrorRecord.Exception.Message)
  }

  return ($parts | Select-Object -Unique) -join " | "
}

$token = ""
if ((Test-Path -LiteralPath $TokenPath) -and -not $ForceEnroll) {
  $token = ([System.IO.File]::ReadAllText($TokenPath)).Trim()
  if ($token) {
    Write-Host "Using existing worker token from $TokenPath"
  }
}

if (-not $token) {
  if (-not $EnrollmentCode.Trim()) {
    throw "EnrollmentCode is required because no reusable worker.token exists."
  }

  Write-Host "Enrolling worker '$WorkerId' against $ApiUrl"
  $enrollment = Invoke-RestMethod -Method Post -Uri "$ApiUrl/enroll" -ContentType "application/json" -Body (@{
    enrollment_code = $EnrollmentCode
    worker_id = $WorkerId
  } | ConvertTo-Json)

  if (-not $enrollment.token) { throw "Enrollment response did not contain a token." }
  $token = [string]$enrollment.token
  [System.IO.File]::WriteAllText($TokenPath, $token, [System.Text.UTF8Encoding]::new($false))
}

Protect-WorkerTokenFile -Path $TokenPath

# Persist the usable worker configuration before model synchronization. A model
# readiness failure can then be repaired and this script rerun without consuming
# another one-time enrollment code.
$config = Get-Content -Raw -Encoding UTF8 $ConfigPath | ConvertFrom-Json
$config.worker_id = $WorkerId
$config.worker_api_base_url = $ApiUrl
$config.path_base_dir = $PathBaseDir
$config.auth.token_file = "../worker.token"
$config.processors.face.model_root = "../.models/face"
$config.processors.face.model_name = $ModelPack
$config | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $ConfigPath

$headers = @{
  Authorization = "Bearer $token"
  "X-Worker-Id" = $WorkerId
}

try {
  $manifest = Invoke-RestMethod -Method Get -Uri "$ApiUrl/models/$ModelPack/manifest" -Headers $headers
  New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null

  foreach ($file in $manifest.files) {
    if (-not $file.present) { continue }
    $target = Join-Path $ModelDir $file.name
    $expected = ([string]$file.sha256).ToLowerInvariant()

    if (Test-Path -LiteralPath $target) {
      $existing = (Get-FileHash -Algorithm SHA256 -Path $target).Hash.ToLowerInvariant()
      if ($existing -eq $expected) {
        Write-Host "Model file already current: $($file.name)"
        continue
      }
    }

    $temp = "$target.download"
    Remove-Item -Force $temp -ErrorAction SilentlyContinue
    Invoke-WebRequest -UseBasicParsing -Uri "$ApiUrl/models/$ModelPack/files/$($file.name)" -Headers $headers -OutFile $temp
    $actual = (Get-FileHash -Algorithm SHA256 -Path $temp).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
      Remove-Item -Force $temp -ErrorAction SilentlyContinue
      throw "SHA-256 mismatch for $($file.name): expected $expected, got $actual"
    }
    Move-Item -Force $temp $target
  }
  $manifest | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $ModelDir "manifest.json")
} catch {
  $details = Get-WorkerApiErrorDetail -ErrorRecord $_
  throw "Worker token and configuration were saved, but model synchronization failed. Rerun this command after resolving the NAS-side condition; the existing worker.token will be reused. API details: $details"
}

Write-Host "Worker enrolled and model files synchronized."
Write-Host "Config: $ConfigPath"
Write-Host "Token:  $TokenPath"
Write-Host "Models: $ModelDir"
