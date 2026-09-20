param(
  [Parameter(Mandatory = $true)][string]$SqlFile,
  [string]$User = 'root',
  [string]$Password = '16954904lk'
)

if (-not (Test-Path -LiteralPath $SqlFile)) {
  Write-Error "SQL file not found: $SqlFile"
  exit 1
}

$content = Get-Content -LiteralPath $SqlFile -Raw -Encoding UTF8
$args = @(
  '--default-character-set=utf8mb4',
  "-u$User",
  "-p$Password"
)

$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$output = $content | & mysql @args 2>&1
$code = $LASTEXITCODE
$ErrorActionPreference = $prevEap

foreach ($line in $output) {
  if ($line -match '^\s*ERROR\s') {
    Write-Host $line
  } elseif ($line -notmatch 'Using a password on the command line') {
    Write-Host $line
  }
}

if ($code -ne 0) { exit $code }
exit 0
