# WB 2002 Workflow

## Files

- `fetch_booth_urls.py`: Crawls district -> AC -> booth pages and exports booth PDF URLs to Excel.
- `download_booth_pdfs.py`: Uses Selenium + Chrome to download booth PDFs from the Excel URL list.

## Typical run order

1. `python code/scripts/wb_2002/fetch_booth_urls.py`
2. `python code/scripts/wb_2002/download_booth_pdfs.py`

## Input/Output expectations

- URL inventory Excel path: `data/raw/ceowestbengal/all_booth_urls.xlsx`
- Backward-compatible fallback path: `data/raw/ceowestbengal/all_booths_urls.xlsx`
- Download destination (default): `data/raw/ceowestbengal/pdfs/`
