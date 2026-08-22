# Data lineage

```text
E:\Electoral roll\ceowestbengal\asd_sir\asd\*.pdf
  -> audit_pdf_corpus.py
     -> data/metadata/wb_2025_asd/pdf_manifest.csv
     -> data/metadata/wb_2025_asd/audit_summary.json
  -> extract_removed_electors.py
     -> data/interim/wb_2025_asd/removed_electors_raw.csv
     -> data/interim/wb_2025_asd/extraction_qa.json
  -> future validated normalization step
     -> data/processed/wb_2025_asd/removed_electors.*
```

The PDF directory is read-only input. The interim dataset has one row per detected
elector table row. Its intended key is `(document_id, serial_number_raw)`, and every
row retains PDF/page/table/row coordinates. No merge, translation, category coding,
or sample restriction occurs during extraction.

The processed stage must preserve every interim row, assert key uniqueness, convert
numeric fields with explicit failure flags, and map multilingual categories through
version-controlled lookup tables. Any exclusions must be written to a rejection table.
