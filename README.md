# Electoral Rolls West Bengal

This repository contains data engineering workflows for electoral roll PDF collection in West Bengal across two pipelines:

- 2002-style booth roll collection from `ceowestbengal.nic.in`
- 2025 ASD/MOM collection from `ceowestbengal.wb.gov.in/asd_sir/`

## Repository layout

```text
.
├─ code/
│  ├─ scripts/
│  │  ├─ wb_2002/
│  │  │  ├─ fetch_booth_urls.py
│  │  │  └─ download_booth_pdfs.py
│  │  └─ wb_2025/
│  │     ├─ electoral_roll_wb_2025.py
│  │     └─ retry_failed_manifest_downloads.py
│  └─ utils/
├─ data/
│  ├─ raw/
│  │  └─ ceowestbengal/
│  │     ├─ all_booth_urls.xlsx
│  │     └─ asd_sir/
│  ├─ interim/
│  ├─ processed/
│  └─ metadata/
└─ PROJECT_LOG.md
```

## Pipeline A: WB 2002 booth rolls (nic.in)

Step 1: collect booth-level PDF URLs into Excel

```bash
python code/scripts/wb_2002/fetch_booth_urls.py
```

- Produces `data/raw/ceowestbengal/all_booth_urls.xlsx`.

Step 2: download booth PDFs from Excel URL list

```bash
python code/scripts/wb_2002/download_booth_pdfs.py
```

- Reads `data/raw/ceowestbengal/all_booth_urls.xlsx` (and falls back to legacy `all_booths_urls.xlsx` if present).
- Writes downloaded files under `data/raw/ceowestbengal/pdfs/<AC No - AC Name>/`.
- Uses Selenium + Chrome and retries each booth up to 3 times.

## Pipeline B: WB 2025 ASD/MOM rolls (wb.gov.in)

Collect and download ASD/MOM PDFs directly from public JSON endpoints:

```bash
python code/scripts/wb_2025/electoral_roll_wb_2025.py --doc-type both --workers 6
```

Useful examples:

```bash
python code/scripts/wb_2025/electoral_roll_wb_2025.py --list-districts
python code/scripts/wb_2025/electoral_roll_wb_2025.py --district COOCHBEHAR --doc-type asd --workers 6
python code/scripts/wb_2025/electoral_roll_wb_2025.py --district 1 --max-files 10 --dry-run
```

Defaults:

- Output root: `D:\Electoral roll\ceowestbengal\asd_sir\`
- Manifest: `D:\Electoral roll\ceowestbengal\asd_sir\manifest.csv`

## Retry failed 2025 downloads

Retry only rows whose latest manifest status is failed:

```bash
python code/scripts/wb_2025/retry_failed_manifest_downloads.py --workers 8
```

Targeted retry examples:

```bash
python code/scripts/wb_2025/retry_failed_manifest_downloads.py --doc-type asd
python code/scripts/wb_2025/retry_failed_manifest_downloads.py --max-retries 100
python code/scripts/wb_2025/retry_failed_manifest_downloads.py --dry-run
```

## Dependencies

Minimum Python version: 3.10+

Core packages used across scripts:

- `requests`
- `beautifulsoup4`
- `pandas`
- `openpyxl` (for Excel I/O)
- `selenium` (for browser-based PDF downloads in 2002 flow)

Install all workflow requirements with:

```bash
pip install -r requirements.txt
```

Or install only one workflow:

```bash
pip install -r requirements/wb_2002.txt
pip install -r requirements/wb_2025.txt
```

## Build GitHub Release assets (large PDF folders)

Use this when data is too large for git commits but each file is below GitHub's release-asset limit.

Main builder script:

```bash
python code/scripts/release/build_release_assets.py \
	--source "wb-2002=C:\Users\anind\Downloads\WB_2002_Electoral_Rolls_Downloader_2025-main\Data" \
	--source "wb-2025=D:\Electoral roll\ceowestbengal\asd_sir" \
	--output-dir "data/release_assets" \
	--max-part-size-gb 1.8 \
	--compression stored \
	--preserve-root-folder \
	--tag "wb-electoral-rolls-data-2026-04-12"
```

PowerShell helper with the same directories:

```powershell
powershell -ExecutionPolicy Bypass -File code/scripts/release/run_build_release_assets.ps1
```

What it generates in `data/release_assets/`:

- Chunked zip parts by dataset (`*_part001.zip`, `*_part002.zip`, ...)
- `sha256sums.txt` with checksums for every zip
- `release_notes.md` for release description
- `gh_release_commands.txt` with ready-to-run `gh release` upload commands

Rerun behavior:

- Existing dataset zip parts in `data/release_assets/<dataset>/` are cleaned before rebuilding, so stale parts are not accidentally uploaded on the next release publish.

Recommendation:

- Keep `--max-part-size-gb` at `1.8` or lower so every zip part stays under 2 GB.
- `--preserve-root-folder` keeps each source folder tree rooted as `Data/...` and `asd_sir/...` inside zip assets.

Publish assets to GitHub Release automatically:

```powershell
powershell -ExecutionPolicy Bypass -File code/scripts/release/publish_release_assets.ps1 -Tag "wb-electoral-rolls-data-2026-04-12"
```

Preview publish commands without uploading:

```powershell
powershell -ExecutionPolicy Bypass -File code/scripts/release/publish_release_assets.ps1 -Tag "wb-electoral-rolls-data-2026-04-12" -DryRun
```

Low-disk stream upload path:

```powershell
powershell -ExecutionPolicy Bypass -File code/scripts/release/run_stream_release_upload.ps1 -Tag "wb-electoral-rolls-data-2026-04-12" -Clobber
```

This mode builds one zip part at a time in temporary storage, uploads it to the GitHub Release, and deletes the local part immediately. It also:

- writes metadata files under `data/release_assets_stream/`
- uploads `<tag>_notes.md` and `<tag>_sha256sums.txt` as release assets
- updates the release description with the generated upload summary
- removes stale `*_partNNN.zip` assets for a dataset when `-Clobber` is used

Preview the stream plan without uploading:

```powershell
powershell -ExecutionPolicy Bypass -File code/scripts/release/run_stream_release_upload.ps1 -Tag "wb-electoral-rolls-data-2026-04-12" -DryRun
```

## Notes

- The 2025 flow includes SSL compatibility handling for environments where legacy renegotiation causes handshake failures.
- The 2025 site shows a browser CAPTCHA modal, but the script uses public endpoint data and direct PDF links.
- Some source URLs may remain permanently unavailable (for example HTTP 404 at source).