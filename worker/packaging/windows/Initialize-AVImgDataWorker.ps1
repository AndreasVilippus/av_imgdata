param(
  [Parameter(Mandatory=$true)][string]$ApiUrl,
  [Parameter(Mandatory=$true)][string]$EnrollmentCode,
  [Parameter(Mandatory=$true)][string]$WorkerId,
  [Parameter(Mandatory=$true)][string]$PathBaseDir,
  [string]$ModelPack = "buffalo_l",
  [string]$ConfigPath = "$PSScriptRoot\..\..\config\worker-config.example.json"
)

$ErrorActionPreference = "Stop"
$ApiUrl = $ApiUrl.TrimEnd('/')
$BundleRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
$TokenPath = Join-Path $BundleRoot "worker.token"
$ModelRoot = Join-Path $BundleRoot ".models\face"
$ModelDir = Join-Path $ModelRoot $ModelPack

Write-Host "Enrolling worker '$WorkerId' against $ApiUrl"
$enrollment = Invoke-RestMethod -Method Post -Uri "$ApiUrl/enroll" -ContentType "application/json" -Body (@{
  enrollment_code = $EnrollmentCode
  worker_id = $WorkerId
} | ConvertTo-Json)

if (-not $enrollment.token) { throw "Enrollment response did not contain a token." }
[System.IO.File]::WriteAllText($TokenPath, [string]$enrollment.token, [System.Text.UTF8Encoding]::new($false))

# Restrict token file to the current Windows account.
& icacls.exe $TokenPath /inheritance:r /grant:r "$env:USERNAME:(R,W)" | Out-Null

$headers = @{
  Authorization = "Bearer $($enrollment.token)"
  "X-Worker-Id" = $WorkerId
}
$manifest = Invoke-RestMethod -Method Get -Uri "$ApiUrl/models/$ModelPack/manifest" -Headers $headers
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null

foreach ($file in $manifest.files) {
  if (-not $file.present) { continue }
  $target = Join-Path $ModelDir $file.name
  $temp = "$target.download"
  Invoke-WebRequest -UseBasicParsing -Uri "$ApiUrl/models/$ModelPack/files/$($file.name)" -Headers $headers -OutFile $temp
  $actual = (Get-FileHash -Algorithm SHA256 -Path $temp).Hash.ToLowerInvariant()
  $expected = ([string]$file.sha256).ToLowerInvariant()
  if ($actual -ne $expected) {
    Remove-Item -Force $temp -ErrorAction SilentlyContinue
    throw "SHA-256 mismatch for $($file.name): expected $expected, got $actual"
  }
  Move-Item -Force $temp $target
}
$manifest | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $ModelDir "manifest.json")

$config = Get-Content -Raw -Encoding UTF8 $ConfigPath | ConvertFrom-Json
$config.worker_id = $WorkerId
$config.worker_api_base_url = $ApiUrl
$config.path_base_dir = $PathBaseDir
$config.auth.token_file = "../worker.token"
$config.processors.face.model_root = "../.models/face"
$config.processors.face.model_name = $ModelPack
$config | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $ConfigPath

Write-Host "Worker enrolled and model files synchronized."
Write-Host "Config: $ConfigPath"
Write-Host "Token:  $TokenPath"
Write-Host "Models: $ModelDir"
