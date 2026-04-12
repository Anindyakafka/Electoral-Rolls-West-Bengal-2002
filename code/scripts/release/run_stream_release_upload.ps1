param(
    [string]$Repo = "Anindyakafka/Electoral-Rolls-West-Bengal-2002",
    [string]$Tag = "wb-electoral-rolls-data-2026-04-12",
    [string]$TokenEnv = "GITHUB_TOKEN",
    [string]$TempDir = "D:\release_stream_temp",
    [switch]$Clobber,
    [switch]$DryRun
)

$python = "C:/Users/anind/AppData/Local/Programs/Python/Python313/python.exe"
$scriptPath = Join-Path $PSScriptRoot "stream_release_upload.py"
$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$metaDir = Join-Path $repoRoot "data/release_assets_stream"

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
    "--source", "wb-2002=C:\Users\anind\Downloads\WB_2002_Electoral_Rolls_Downloader_2025-main\Data",
    "--source", "wb-2025=D:\Electoral roll\ceowestbengal\asd_sir",
    "--temp-dir", $TempDir,
    "--metadata-dir", $metaDir,
    "--max-part-size-gb", "1.8",
    "--compression", "stored",
    "--preserve-root-folder",
    "--token-env", $TokenEnv
)

if ($Clobber) { $args += "--clobber" }
if ($DryRun) { $args += "--dry-run" }

& $python @args
if ($LASTEXITCODE -ne 0) {
    throw "stream_release_upload.py failed with exit code $LASTEXITCODE"
}
