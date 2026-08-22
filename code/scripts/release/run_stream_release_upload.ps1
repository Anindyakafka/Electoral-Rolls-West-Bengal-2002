param(
    [string]$Repo = "Anindyakafka/Electoral-Rolls-West-Bengal-2002",
    [string]$Tag = "wb-electoral-rolls-2025-2026-04-13",
    [string]$Source = "E:\Electoral roll\ceowestbengal\asd_sir",
    [string]$TokenEnv = "GITHUB_TOKEN",
    [string]$TempDir = "E:\release_stream_temp\wb-2025",
    [string]$Python = "C:/Users/anind/AppData/Local/Programs/Python/Python313/python.exe",
    [switch]$Clobber,
    [switch]$DryRun
)

$scriptPath = Join-Path $PSScriptRoot "stream_release_upload.py"
$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$metaDir = Join-Path $repoRoot "data/release_assets_stream"

if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
    throw "2025 source directory not found: $Source"
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python executable not found: $Python"
}

if (-not $DryRun) {
    $token = [Environment]::GetEnvironmentVariable($TokenEnv, "Process")
    if ([string]::IsNullOrWhiteSpace($token)) {
        $token = [Environment]::GetEnvironmentVariable($TokenEnv, "User")
    }
    if ([string]::IsNullOrWhiteSpace($token)) {
        $token = [Environment]::GetEnvironmentVariable($TokenEnv, "Machine")
    }
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw "Environment variable $TokenEnv is not set. Set it before upload."
    }
}

$args = @(
    $scriptPath,
    "--repo", $Repo,
    "--tag", $Tag,
    "--source", "wb-2025=$Source",
    "--temp-dir", $TempDir,
    "--metadata-dir", $metaDir,
    "--max-part-size-gb", "1.8",
    "--compression", "stored",
    "--preserve-root-folder",
    "--token-env", $TokenEnv
)

if ($Clobber) { $args += "--clobber" }
if ($DryRun) { $args += "--dry-run" }

& $Python @args
if ($LASTEXITCODE -ne 0) {
    throw "stream_release_upload.py failed with exit code $LASTEXITCODE"
}
