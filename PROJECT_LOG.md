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
- Added release packaging automation: `code/scripts/release/build_release_assets.py` for chunked zip creation, checksums, and GitHub CLI command generation.
- Added `code/scripts/release/run_build_release_assets.ps1` with configured source paths for the current 2002 and 2025 data directories.
- Documented release packaging flow and commands in root and code READMEs.
- Hardened release rebuilds so old dataset zip parts are removed before regenerating assets.
- Completed the low-disk GitHub Release uploader flow with release-summary updates, metadata asset uploads, and stale streamed-part cleanup under `-Clobber`.
- Expanded README guidance for both prebuilt-asset publishing and one-part-at-a-time stream uploads.
- Verified local source directories for 2002 and 2025 release packaging and confirmed a stream-upload plan of 13 parts for 2002 plus 98 parts for 2025 with preserved source-root structure inside each zip.
- Updated the local on-disk `stream_release_upload.py` checkout to match the hardened uploader logic used in the repo workspace.
- Attempted live release upload with the provided PAT, but GitHub rejected release creation with `403 Resource not accessible by personal access token`; the next step is rerunning the same command with a token that has release creation permissions.
- Retried the live stream upload with a second PAT and received the same `403 Resource not accessible by personal access token` response on `POST /repos/Anindyakafka/Electoral-Rolls-West-Bengal-2002/releases`, confirming the remaining blocker is token permission scope rather than asset structure or local packaging.
- Successfully started stream upload with a PAT that can create releases; mixed tag upload progressed through all 2002 parts and began early 2025 parts.
- Switched to split release strategy on request: stopped the mixed run and started separate stream uploads under tags `wb-electoral-rolls-2002-2026-04-13` and `wb-electoral-rolls-2025-2026-04-13` with isolated temp and metadata directories.

## 2026-08-22
- Added a conventional analysis layout for the WB 2025 ASD corpus with external-raw,
  interim, processed, metadata, notebook, output, and log directories.
- Inventoried 80,655 ASD PDFs across 24 districts and 294 assembly constituencies;
  identified four zero-byte source PDFs under AC 1 Mekliganj.
- Confirmed that the reports expose Unicode text and ruled 10-column tables in Bengali,
  English, and Devanagari, allowing direct extraction without corpus-wide OCR.
- Added document auditing, district-sharded extraction, resumable statewide orchestration,
  lineage documentation, a data dictionary, and final statewide validation tooling.
- Replaced PyMuPDF's high-level table extraction after finding that it displaced Bengali
  combining marks. The production method assigns one page-level word extraction into
  geometric table cells, preserving text while substantially reducing runtime.
- Rebuilt and validated the Kalimpong shard: 293 PDFs, 1,925 pages, and 17,331 records
  with no duplicate keys, serial gaps, missing EPICs, or numeric-field failures.
- Completed and structurally validated the Jhargram shard: 1,101 PDFs, 3,366 pages,
  and 52,786 records. Source-cell tracing showed that 46 missing elector names and 49
  missing relation names arise from invalid glyph mappings in the PDFs, not extractor loss.
- Hardened the GitHub release uploader with transient retries, ambiguous-upload
  reconciliation, incomplete-asset cleanup, and reuse of complete local ZIPs after an
  interrupted transfer.
