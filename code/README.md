# Code

- `scripts/` — one-off or pipeline scripts
- `notebooks/` — exploratory analysis notebooks
- `utils/` — reusable helper code

## Current scraper

- `scripts/electoral_roll_wb_2025.py` downloads the public ASD / BLO-BLA PDF lists from `https://ceowestbengal.wb.gov.in/asd_sir/`.
- Default output goes to `D:\Electoral roll\ceowestbengal\asd_sir\`.
- Parallel workers are supported with `--workers` for faster district/file processing.
- Example: `python code/scripts/electoral_roll_wb_2025.py --district COOCHBEHAR --doc-type asd --workers 6`
