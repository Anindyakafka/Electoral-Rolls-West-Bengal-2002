# Project Log

## 2026-04-11
- Created a standard starter structure for `data/` and `code/` folders.
- Added placeholder files so the folders are preserved in the repository.
- Added `code/scripts/electoral_roll_wb_2025.py` to collect district-wise AC/part PDF links from the CEO West Bengal ASD/SIR page.
- Routed scraper output to `data/raw/ceowestbengal/asd_sir/` and added a download manifest layout.
- Added SSL compatibility for Python 3.13 / OpenSSL 3 so the downloader can connect to the CEO West Bengal site locally.
- Added parallel worker support (`--workers`) so multiple districts and PDFs can be processed concurrently.
- Changed the scraper default output location to `D:\Electoral roll\ceowestbengal\asd_sir\` to avoid low system drive space.
- Added `code/scripts/retry_failed_manifest_downloads.py` to retry only latest manifest failures and write files back to `D:\Electoral roll\...` paths.

## 2026-04-12
- Restructured `code/scripts/` into workflow folders: `wb_2002/` and `wb_2025/`.
- Moved scripts into their respective workflow folders and removed duplicated top-level script copies.
- Updated `code/scripts/wb_2025/electoral_roll_wb_2025.py` path assumptions after move (repo root resolution and usage examples).
- Rewrote root `README.md` with full project documentation, commands, dependencies, and pipeline descriptions.
- Updated `code/README.md` to reflect new script layout and command paths.
- Added per-workflow documentation files: `code/scripts/wb_2002/README.md` and `code/scripts/wb_2025/README.md`.
- Added dependency manifests: `requirements.txt`, `requirements/wb_2002.txt`, and `requirements/wb_2025.txt`.
- Updated WB 2002 scripts to use repo-anchored input/output defaults under `data/raw/ceowestbengal/`.
- Standardized WB 2002 canonical URL inventory filename to `all_booth_urls.xlsx` with fallback support for legacy `all_booths_urls.xlsx`.
