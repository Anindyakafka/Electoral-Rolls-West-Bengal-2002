param(
    [string]$Tag = "wb-electoral-rolls-data-2026-04-12",
    [string]$AssetsDir = "",
    [switch]$DryRun
)

$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
if ([string]::IsNullOrWhiteSpace($AssetsDir)) {
    $AssetsDir = Join-Path $repoRoot "data/release_assets"
}

$notesFile = Join-Path $AssetsDir "release_notes.md"
$checksumsFile = Join-Path $AssetsDir "sha256sums.txt"

if (-not (Test-Path $AssetsDir)) {
    throw "Assets directory not found: $AssetsDir"
}

if (-not (Test-Path $notesFile)) {
    throw "Missing release notes file: $notesFile"
}

if (-not (Test-Path $checksumsFile)) {
    throw "Missing checksums file: $checksumsFile"
}

$zipFiles = Get-ChildItem -Path $AssetsDir -Recurse -File -Filter "*.zip" | Sort-Object FullName
if (-not $zipFiles -or $zipFiles.Count -eq 0) {
    throw "No zip assets found under: $AssetsDir"
}

$createCmd = "gh release create $Tag --title `"$Tag`" --notes-file `"$notesFile`""
$uploadChecksumCmd = "gh release upload $Tag `"$checksumsFile`" --clobber"

Write-Host "Tag: $Tag"
Write-Host "Assets directory: $AssetsDir"
Write-Host "Zip assets found: $($zipFiles.Count)"

if ($DryRun) {
    Write-Host "\n[DRY-RUN] Would run:"
    Write-Host $createCmd
    Write-Host $uploadChecksumCmd
    foreach ($zip in $zipFiles) {
        Write-Host "gh release upload $Tag `"$($zip.FullName)`" --clobber"
    }
    exit 0
}

& gh release view $Tag *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating release $Tag ..."
    Invoke-Expression $createCmd
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create release: $Tag"
    }
} else {
    Write-Host "Release $Tag already exists."
}

Write-Host "Uploading checksums ..."
Invoke-Expression $uploadChecksumCmd
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upload checksums file"
}

foreach ($zip in $zipFiles) {
    $cmd = "gh release upload $Tag `"$($zip.FullName)`" --clobber"
    Write-Host "Uploading: $($zip.Name)"
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upload asset: $($zip.FullName)"
    }
}

Write-Host "Done. All assets uploaded to release: $Tag"
