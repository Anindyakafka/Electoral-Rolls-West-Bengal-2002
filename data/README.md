# Data

- `raw/`: immutable inputs or pointers to external immutable inputs.
- `interim/`: reproducible extractions that retain source values and row lineage.
- `processed/`: validated, normalized, analysis-ready datasets.
- `metadata/`: source manifests, schemas, codebooks, mappings, and QA summaries.

Large generated datasets are ignored by git. Each dataset-specific subdirectory must
document its source, generating script, grain, identifiers, and known limitations.
