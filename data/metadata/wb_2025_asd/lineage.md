# Data lineage

```text
E:\Electoral roll\ceowestbengal\asd_sir\asd\*.pdf
  -> audit_pdf_corpus.py
     -> data/metadata/wb_2025_asd/pdf_manifest.csv
     -> data/metadata/wb_2025_asd/audit_summary.json
  -> extract_removed_electors.py
     -> data/interim/wb_2025_asd/shards/<district>.csv
     -> data/interim/wb_2025_asd/shards/<district>_qa.json
  -> run_statewide_extraction.py
     -> data/interim/wb_2025_asd/removed_electors_raw.csv
     -> data/interim/wb_2025_asd/statewide_extraction_qa.json
  -> validate_statewide_dataset.py
     -> data/interim/wb_2025_asd/statewide_validation.json
  -> build_missing_name_manifest.py
     -> data/interim/wb_2025_asd/missing_name_cells.csv
     -> data/interim/wb_2025_asd/missing_name_cells_summary.json
  -> classify_missing_name_cells.py
     -> data/interim/wb_2025_asd/missing_name_source_classification.csv
     -> data/interim/wb_2025_asd/missing_name_source_classification.json
  -> build_analysis_dataset.py
     -> data/processed/wb_2025_asd/removed_electors_clean.csv.gz
     -> data/processed/wb_2025_asd/cleaning_qa.json
```

The PDF directory is read-only input. The interim dataset has one row per detected
elector table row. Its intended key is `(document_id, serial_number_raw)`, and every
row retains PDF/page/table/row coordinates. No merge, translation, category coding,
or sample restriction occurs during extraction.

The completed interim dataset contains 5,819,543 rows from 80,651 readable PDFs. All
80,655 source paths are accounted for; four zero-byte PDFs are retained in extraction
QA as documented source errors. Verified source anomalies are recorded in
`known_source_anomalies.csv`, and raw values are not silently corrected.

All 6,979 blank name fields have row-level source classifications. Of these, 6,924
are encoded in the PDFs exclusively as CID 0, which maps to the font's undefined
`.notdef` square and contains no recoverable character identity; the other 55 source
cells contain no characters. The audit found no extraction loss and no undecodable
nonzero glyph that could be recovered through a font map or OCR. Their EPIC IDs and
full PDF coordinates are retained for a future authoritative cross-reference.

The completed processed stage preserves every interim row, asserts key uniqueness, converts
validated numeric fields, maps every multilingual category to a canonical analysis code,
retains raw category values, and adds explicit source-damage and age-anomaly flags. It makes
no exclusions, imputations, name translations, or silent corrections.
