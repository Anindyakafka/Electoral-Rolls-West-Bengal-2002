# Code

- `scripts/` — one-off or pipeline scripts
- `notebooks/` — exploratory analysis notebooks
- `utils/` — reusable helper code

## Current scraper

- `scripts/electoral_roll_wb_2025.py` downloads the public ASD / BLO-BLA PDF lists from `https://ceowestbengal.wb.gov.in/asd_sir/`.
- Output goes to `../data/raw/ceowestbengal/asd_sir/`.
- Example: `python code/scripts/electoral_roll_wb_2025.py --district COOCHBEHAR --doc-type asd`
