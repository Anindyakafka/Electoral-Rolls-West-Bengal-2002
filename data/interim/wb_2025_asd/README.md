# WB 2025 ASD interim data

`removed_electors_raw.csv` is the append-free, singular extraction output. Values
retain the source language and receive a `_raw` suffix. Every row carries its PDF,
page, table, and source-row lineage. Generated files in this directory are ignored.

The directory also contains resumable district shards, statewide extraction/validation
QA, the missing-name cell manifest, and a glyph-level source classification sidecar.
These are reproducible intermediates; analysis should use the processed compressed CSV.
