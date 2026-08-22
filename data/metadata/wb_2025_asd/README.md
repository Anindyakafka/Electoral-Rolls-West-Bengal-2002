# WB 2025 ASD metadata

- `pdf_manifest.csv` (generated): one row per source PDF with structural QA.
- `audit_summary.json` (generated): aggregate corpus diagnostics.
- `data_dictionary.csv`: proposed row-level schema.
- `obstacles.md`: observed extraction and analysis risks.
- `lineage.md`: source-to-output transformation and validation contract.
- `audit_report.md`: current corpus inventory and pilot findings.
- `known_source_anomalies.csv`: verified source defects and implausible values;
  raw extracted values are retained and explicitly flagged for downstream cleaning.
