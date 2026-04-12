# Code

- `scripts/` — workflow scripts grouped by data source/year
- `notebooks/` — exploratory analysis notebooks
- `utils/` — reusable helper code

## Scripts layout

- `scripts/wb_2002/fetch_booth_urls.py` builds booth URL inventory from `ceowestbengal.nic.in` into an Excel file.
- `scripts/wb_2002/download_booth_pdfs.py` reads the Excel file and downloads booth PDFs via Selenium.
- `scripts/wb_2025/electoral_roll_wb_2025.py` downloads ASD/MOM PDFs from `https://ceowestbengal.wb.gov.in/asd_sir/` JSON-backed endpoints.
- `scripts/wb_2025/retry_failed_manifest_downloads.py` retries only latest failed entries from the 2025 manifest.

## Quick commands

- `python code/scripts/wb_2002/fetch_booth_urls.py`
- `python code/scripts/wb_2002/download_booth_pdfs.py`
- `python code/scripts/wb_2025/electoral_roll_wb_2025.py --doc-type both --workers 6`
- `python code/scripts/wb_2025/retry_failed_manifest_downloads.py --workers 8`
