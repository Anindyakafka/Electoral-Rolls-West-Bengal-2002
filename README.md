# West Bengal Electoral Roll Data

Reproducible collection, extraction, validation, and analysis-preparation workflows for
West Bengal electoral-roll data. The repository covers two distinct sources:

- WB 2002 booth-level electoral-roll PDFs.
- WB 2025 ASD/SIR documents, including the row-level list of electors whose enumeration
  forms were reported as uncollectable.

Large PDFs and generated datasets are published through GitHub Releases or kept in the
documented external data directory. Git contains the code, schemas, mappings, QA summaries,
and provenance records needed to rebuild them.

## Current status

The WB 2025 ASD extraction and cleaning pipeline is complete.

| Item | Result |
|---|---:|
| Source ASD PDFs inventoried | 80,655 |
| Readable PDFs | 80,651 |
| Documented zero-byte PDFs | 4 |
| Extracted elector records | 5,819,543 |
| Duplicate document/serial keys | 0 |
| Records missing an EPIC ID | 0 |
| Analysis categories left unmapped | 0 |
| Name cells destroyed as CID-0 in source | 6,924 |
| Genuinely blank source name cells | 55 |

The source PDFs call these records “uncollectable.” This repository does not assume that
every record represents a legally final deletion.

## Repository layout

```text
code/
  notebooks/                 exploratory and analysis notebooks
  scripts/
    wb_2002/                 2002 URL collection and PDF download
    wb_2025/                 2025 ASD/MOM discovery and download
    wb_2025_asd/             ASD audit, extraction, validation, and cleaning
    release/                 GitHub Release packaging and resumable upload
data/
  raw/                       immutable inputs or pointers to external inputs
  interim/wb_2025_asd/       source-faithful extraction and QA sidecars
  processed/wb_2025_asd/     analysis-ready generated dataset
  metadata/wb_2025_asd/      dictionary, mappings, anomalies, and lineage
outputs/
  figures/                   generated figures
  tables/                    generated tables
  logs/                      pipeline logs
requirements/                workflow-specific Python dependencies
```

## WB 2025 ASD pipeline

The external source directory used by default is:

```text
E:\Electoral roll\ceowestbengal\asd_sir\asd
```

Install dependencies and run the source audit and extraction:

```powershell
python -m pip install -r requirements/wb_2025_analysis.txt
python code/scripts/wb_2025_asd/audit_pdf_corpus.py
python code/scripts/wb_2025_asd/run_statewide_extraction.py --workers 4
```

The statewide runner creates resumable district shards, combines them, and executes the
final validation gates. It produces the source-faithful interim file
`data/interim/wb_2025_asd/removed_electors_raw.csv`.

Audit absent names and build the analysis-ready dataset:

```powershell
python code/scripts/wb_2025_asd/build_missing_name_manifest.py
python code/scripts/wb_2025_asd/classify_missing_name_cells.py
python code/scripts/wb_2025_asd/build_analysis_dataset.py
python code/scripts/wb_2025_asd/validate_analysis_dataset.py
```

The final generated file is
`data/processed/wb_2025_asd/removed_electors_clean.csv.gz`. It has one row per elector,
stable `record_id`, numeric identifiers, normalized names, canonical category codes,
retained source-language categories, name-source status flags, an age-outlier flag, and
complete PDF/page/table/row lineage. The raw extraction is never overwritten and no rows
are filtered during cleaning.

Key documentation:

- [`data_dictionary.csv`](data/metadata/wb_2025_asd/data_dictionary.csv)
- [`category_mappings.csv`](data/metadata/wb_2025_asd/category_mappings.csv)
- [`lineage.md`](data/metadata/wb_2025_asd/lineage.md)
- [`known_source_anomalies.csv`](data/metadata/wb_2025_asd/known_source_anomalies.csv)
- [`obstacles.md`](data/metadata/wb_2025_asd/obstacles.md)

Read the compressed dataset in chunks when memory is limited:

```python
import pandas as pd

path = "data/processed/wb_2025_asd/removed_electors_clean.csv.gz"
for chunk in pd.read_csv(path, chunksize=250_000):
    # analysis here
    pass
```

The statuses `destroyed_cid0_notdef` and `source_blank` are source limitations, not
missingness introduced during extraction. CID 0 maps to the font's undefined square, so
those names require matching to another authoritative roll by EPIC or old-part/old-serial
identifiers; they must not be guessed.

## WB 2002 pipeline

```powershell
python code/scripts/wb_2002/fetch_booth_urls.py
python code/scripts/wb_2002/download_booth_pdfs.py
```

The URL inventory is `data/raw/ceowestbengal/all_booth_urls.xlsx`. See
[`code/scripts/wb_2002/README.md`](code/scripts/wb_2002/README.md) for browser and path
requirements.

## WB 2025 document download

```powershell
python code/scripts/wb_2025/electoral_roll_wb_2025.py --doc-type both --workers 6
python code/scripts/wb_2025/retry_failed_manifest_downloads.py --workers 8
```

See [`code/scripts/wb_2025/README.md`](code/scripts/wb_2025/README.md) for selectors and
output-path options.

## GitHub Release uploads

The low-disk uploader builds, uploads, verifies, and removes one local ZIP part at a time.
It safely resumes by skipping complete release assets:

```powershell
$env:GITHUB_TOKEN = "<fine-grained PAT with Contents: read and write>"
powershell -NoProfile -ExecutionPolicy Bypass `
  -File code/scripts/release/run_stream_release_upload.ps1
```

Defaults:

- Repository: `Anindyakafka/Electoral-Rolls-West-Bengal-2002`
- Tag: `wb-electoral-rolls-2025-2026-04-13`
- Source: `E:\Electoral roll\ceowestbengal\asd_sir`
- Maximum ZIP part size: 1.8 GB

Do not commit access tokens. `-Clobber` intentionally replaces existing assets and should
not be used for an ordinary resume.

## Reproducibility rules

- External PDFs are immutable inputs.
- Generated datasets, logs, and release assets are ignored by Git.
- Every processed row retains its source coordinates.
- Cleaning fails if a category is unmapped or a missing name lacks a source classification.
- Source anomalies remain unchanged and are represented through flags and metadata.
- Dataset lineage and material workflow changes are recorded in `PROJECT_LOG.md`.

## License

See [`LICENSE`](LICENSE). Source electoral documents remain subject to the terms and legal
status of their issuing authorities.
