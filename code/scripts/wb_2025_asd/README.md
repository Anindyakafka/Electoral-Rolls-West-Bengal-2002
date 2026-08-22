# WB 2025 ASD analysis pipeline

This workflow converts the booth-level PDF reports in the external source directory
into a single row-level dataset while retaining source-file and page lineage.

Default external source:

`E:\Electoral roll\ceowestbengal\asd_sir\asd`

## Stages

1. Audit every PDF and build a document manifest:

   ```powershell
   python code/scripts/wb_2025_asd/audit_pdf_corpus.py
   ```

2. Run a bounded extraction pilot:

   ```powershell
   python code/scripts/wb_2025_asd/extract_removed_electors.py --limit 1000
   ```

   Or create a resumable district shard while other disk-heavy work is active:

   ```powershell
   python code/scripts/wb_2025_asd/extract_removed_electors.py `
     --district 23 `
     --output data/interim/wb_2025_asd/shards/23_kalimpong.csv `
     --qa data/interim/wb_2025_asd/shards/23_kalimpong_qa.json `
     --workers 1
   ```

3. After reviewing pilot QA, run the full extraction:

   ```powershell
   python code/scripts/wb_2025_asd/run_statewide_extraction.py --workers 4
   ```

   The statewide runner creates resumable district shards, skips shards whose PDF
   counts and QA already pass, combines them only after all districts complete, and
   runs `validate_statewide_dataset.py` as the final acceptance gate.

4. Materialize and classify every blank name field:

   ```powershell
   python code/scripts/wb_2025_asd/build_missing_name_manifest.py
   python code/scripts/wb_2025_asd/classify_missing_name_cells.py
   ```

   The classification reads the PDF character and glyph records at the exact table-cell
   coordinates. In the completed corpus, all 6,979 blank name cells are accounted for:
   6,924 contain only CID 0 / `.notdef` glyphs and 55 are genuinely empty. There are no
   extractor-loss or nonzero-glyph cases. CID 0 is the font's undefined glyph and carries
   no character identity; OCR sees only identical square boxes, so filling those names
   requires a separate authoritative source keyed by `epic_number_raw`. Never guess them.

   `recover_missing_names_ocr.py` is retained for a future source containing visible but
   non-searchable name glyphs. It writes an append-only sidecar and never overwrites raw
   extraction values; it cannot reconstruct the CID-0 cells in this corpus.

5. Build the row-preserving analysis dataset:

   ```powershell
   python code/scripts/wb_2025_asd/build_analysis_dataset.py
   ```

   This creates `data/processed/wb_2025_asd/removed_electors_clean.csv.gz` and its
   `cleaning_qa.json`. The cleaner converts validated numeric fields, standardizes every
   multilingual category, retains source-language values and lineage, attaches name-source
   statuses, and fails if any row, mapping, or missing-name classification is unaccounted for.

   Independently validate the generated file and its gzip stream:

   ```powershell
   python code/scripts/wb_2025_asd/validate_analysis_dataset.py
   ```

Generated CSVs are deliberately ignored by git. Commit code, schemas, summaries,
and documentation; publish large generated datasets separately.
