# WB 2025 ASD/MOM Workflow

## Files

- `electoral_roll_wb_2025.py`: Collects district/AC/PS PDF links and downloads ASD/MOM files.
- `retry_failed_manifest_downloads.py`: Retries only latest failed rows from `manifest.csv`.

## Typical run order

1. `python code/scripts/wb_2025/electoral_roll_wb_2025.py --doc-type both --workers 6`
2. `python code/scripts/wb_2025/retry_failed_manifest_downloads.py --workers 8`

## Default paths

- Output root: `D:\Electoral roll\ceowestbengal\asd_sir\`
- Manifest: `D:\Electoral roll\ceowestbengal\asd_sir\manifest.csv`
