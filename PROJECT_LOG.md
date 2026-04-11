# Project Log

## 2026-04-11
- Created a standard starter structure for `data/` and `code/` folders.
- Added placeholder files so the folders are preserved in the repository.
- Added `code/scripts/electoral_roll_wb_2025.py` to collect district-wise AC/part PDF links from the CEO West Bengal ASD/SIR page.
- Routed scraper output to `data/raw/ceowestbengal/asd_sir/` and added a download manifest layout.
- Added SSL compatibility for Python 3.13 / OpenSSL 3 so the downloader can connect to the CEO West Bengal site locally.
- Added parallel worker support (`--workers`) so multiple districts and PDFs can be processed concurrently.
