# Observed extraction and analysis obstacles

1. The corpus is multilingual: Bengali dominates, with English and Devanagari reports.
2. Unicode text is present, but visually identical Bengali strings may use different
   combining-code-point sequences; retain raw text and normalize only derived fields.
3. Four source PDFs are zero bytes and cannot yield records.
4. Headers repeat on each page and must not be interpreted as elector records.
5. Cell text wraps across lines. Extraction must collapse layout line breaks without
   destroying characters or word boundaries.
6. Category labels for gender, relationship, and reason vary by language and require
   explicit mapping tables rather than ad-hoc translation.
7. EPIC identifiers include both modern compact forms and older slash-delimited forms;
   store them as strings and never coerce them to numbers.
8. AC and part identifiers occur in both paths and filenames. Disagreement is a QA
   failure, not something to resolve silently.
9. A document may legitimately contain no elector rows, but this must be distinguished
   from table-detection failure or file corruption.
10. The list describes people whose enumeration forms were not received. Treating every
    row as a legally final deletion requires substantive confirmation from election
    documentation; the dataset should initially use `uncollectable` terminology.
11. The source generator replaced 6,924 name cells with repeated CID 0 characters.
    CID 0 maps to the embedded font's `.notdef` square: the PDF contains neither the
    original Unicode nor distinct visible glyph shapes, so OCR and reverse font mapping
    cannot reconstruct these names. A further 55 name cells are empty in the source.
    Preserve their EPIC identifiers and lineage for matching to another authoritative
    roll; do not infer or fabricate names.
