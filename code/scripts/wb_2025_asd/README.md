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

Generated CSVs are deliberately ignored by git. Commit code, schemas, summaries,
and documentation; publish large generated datasets separately.
