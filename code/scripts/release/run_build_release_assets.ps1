$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))

python "$PSScriptRoot/build_release_assets.py" `
  --source "wb-2002=C:\Users\anind\Downloads\WB_2002_Electoral_Rolls_Downloader_2025-main\Data" `
  --source "wb-2025=D:\Electoral roll\ceowestbengal\asd_sir" `
  --output-dir "$repoRoot/data/release_assets" `
  --max-part-size-gb 1.8 `
  --compression stored `
  --preserve-root-folder `
  --tag "wb-electoral-rolls-data-2026-04-12"
