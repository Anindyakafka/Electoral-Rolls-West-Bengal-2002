# WB 2025 ASD corpus: initial audit report

## Corpus inventory

- External root: `E:\Electoral roll\ceowestbengal\asd_sir\asd`
- District directories: 24
- Assembly-constituency directories: 294
- PDF files: 80,655
- PDF bytes: 5,192,915,197 (4.84 GiB)
- Zero-byte PDFs: 4, all under AC 1 Mekliganj (parts 129, 130, 132, 133)
- Latest download-manifest status: 80,655 downloaded, 25 dry-run, 1 failed

## Format inspection

A deterministic two-document sample from each district (48 PDFs) covered Bengali,
English, and Devanagari reports. Inspected documents were landscape PDF 1.7 files,
had extractable Unicode text, contained no raster page images, and exposed ruled
10-column tables. Page counts in examples ranged from 1 to 16.

The 10 source columns are serial number, EPIC, elector name, relation type, relation
name, old part number, old serial number, age, gender, and uncollectable reason.

## Extraction pilot

A 10-document/39-page geometry-based pilot produced 608 elector rows:

- 39 tables detected, exactly one per page
- all tables had 10 columns
- 39 non-data rows, exactly the repeated page headers
- no duplicate `(document_id, serial_number_raw)` keys
- no missing EPIC values
- all age, old-part, and old-serial values were numeric
- no PDF or table-extraction errors

The pilot observed four Bengali reason categories: permanently shifted, dead, not
found/absent, and already enrolled. These are preliminary and must not become the
final mapping universe until the full extraction is profiled.

A subsequent full Kalimpong shard test covered 293 PDFs, 1,925 pages, and 17,331
records. After switching to single-pass geometric word assignment, it passed with no
duplicate keys, serial gaps, missing EPICs, or nonnumeric age/old-roll identifiers;
observed ages ranged from 18 to 99.

## Critical implementation finding

PyMuPDF's high-level `table.extract()` displaced some Bengali combining marks. Reading
each geometric table cell with `page.get_textbox()` preserved correct text (for example,
`বিজয়` instead of `বিজয ়`). The production extractor uses the geometric method.

## Next gate

Do not run the full extraction while the GitHub release uploader is reading the same
external drive. After that upload finishes, run the full manifest audit followed by a
4-6 worker extraction. The full QA must reconcile document counts, page counts, table
counts, zero-row documents, key duplicates, missing identifiers, numeric conversion
failures, and the complete multilingual category universe before cleaning begins.
