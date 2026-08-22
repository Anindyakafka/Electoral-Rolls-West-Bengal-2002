# Code

- `scripts/` — workflow scripts grouped by data source/year
- `notebooks/` — exploratory analysis notebooks
- `utils/` — reusable helper code

## Scripts layout

- `scripts/wb_2002/fetch_booth_urls.py` builds booth URL inventory from `ceowestbengal.nic.in` into an Excel file.
- `scripts/wb_2002/download_booth_pdfs.py` reads the Excel file and downloads booth PDFs via Selenium.
- `scripts/wb_2025/electoral_roll_wb_2025.py` downloads ASD/MOM PDFs from `https://ceowestbengal.wb.gov.in/asd_sir/` JSON-backed endpoints.
- `scripts/wb_2025/retry_failed_manifest_downloads.py` retries only latest failed entries from the 2025 manifest.
- `scripts/wb_2025_asd/audit_pdf_corpus.py` inventories and audits the 2025 ASD PDF corpus.
- `scripts/wb_2025_asd/extract_removed_electors.py` creates one lineage-preserving row-level CSV from ASD tables.
- `scripts/release/build_release_assets.py` packages large data folders into GitHub Release-ready zip parts with checksums and command output.
- `scripts/release/run_build_release_assets.ps1` runs the release packager with your current 2002 and 2025 source directories.
- `scripts/release/publish_release_assets.ps1` uploads prebuilt zip parts with `gh release upload`.
- `scripts/release/stream_release_upload.py` and `scripts/release/run_stream_release_upload.ps1` support low-disk release uploads by creating, uploading, and deleting one zip part at a time.

## Quick commands

- `python code/scripts/wb_2002/fetch_booth_urls.py`
- `python code/scripts/wb_2002/download_booth_pdfs.py`
- `python code/scripts/wb_2025/electoral_roll_wb_2025.py --doc-type both --workers 6`
- `python code/scripts/wb_2025/retry_failed_manifest_downloads.py --workers 8`
- `python code/scripts/wb_2025_asd/audit_pdf_corpus.py`
- `python code/scripts/wb_2025_asd/extract_removed_electors.py --limit 1000 --workers 4`
- `python code/scripts/release/build_release_assets.py --source "wb-2002=..." --source "wb-2025=..." --output-dir data/release_assets --max-part-size-gb 1.8`
- `powershell -ExecutionPolicy Bypass -File code/scripts/release/run_build_release_assets.ps1`
- `powershell -ExecutionPolicy Bypass -File code/scripts/release/publish_release_assets.ps1 -Tag "wb-electoral-rolls-data-2026-04-12"`
- `powershell -ExecutionPolicy Bypass -File code/scripts/release/run_stream_release_upload.ps1 -Tag "wb-electoral-rolls-data-2026-04-12" -Clobber`
