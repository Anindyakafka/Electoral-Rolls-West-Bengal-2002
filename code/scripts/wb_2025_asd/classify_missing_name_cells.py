#!/usr/bin/env python3
"""Classify every blank name cell from the PDF's character and glyph data."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

try:
    import fitz
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyMuPDF is required: pip install pymupdf") from exc


DEFAULT_SOURCE = Path(r"E:\Electoral roll\ceowestbengal\asd_sir\asd")
DEFAULT_MANIFEST = Path("data/interim/wb_2025_asd/missing_name_cells.csv")
DEFAULT_OUTPUT = Path("data/interim/wb_2025_asd/missing_name_source_classification.csv")
DEFAULT_QA = Path("data/interim/wb_2025_asd/missing_name_source_classification.json")
NAME_COLUMN = {"elector_name_raw": 2, "relation_name_raw": 4}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--qa", type=Path, default=DEFAULT_QA)
    args = parser.parse_args()

    with args.manifest.open("r", encoding="utf-8-sig", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in manifest:
        grouped[row["source_relative_path"]].append(row)

    extra = ["source_condition", "character_count", "undecodable_character_count",
             "cid0_character_count", "nonzero_undecodable_glyph_count", "diagnostic_error"]
    counts: Counter[str] = Counter()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=[*manifest[0].keys(), *extra])
        writer.writeheader()
        for document_index, (relative, rows) in enumerate(grouped.items(), start=1):
            try:
                with fitz.open(args.source / Path(relative)) as document:
                    page_cache: dict[int, tuple[list, list]] = {}
                    for row in rows:
                        page_index = int(row["source_page"]) - 1
                        if page_index not in page_cache:
                            page = document[page_index]
                            page_cache[page_index] = (page.find_tables().tables, page.get_texttrace())
                        tables, traces = page_cache[page_index]
                        table = tables[int(row["source_table"]) - 1]
                        row_index = int(row["source_row"]) - 1
                        col_index = NAME_COLUMN[row["missing_field"]]
                        rectangle = table.cells[col_index * table.row_count + row_index]
                        if rectangle is None:
                            chars = []
                        else:
                            cell = fitz.Rect(rectangle)
                            chars = [
                                char for trace in traces for char in trace.get("chars", ())
                                if cell.x0 <= (char[3][0] + char[3][2]) / 2 < cell.x1
                                and cell.y0 <= (char[3][1] + char[3][3]) / 2 < cell.y1
                            ]
                        undecodable = [char for char in chars if char[0] in (0, 0xFFFD)]
                        cid0 = [char for char in undecodable if char[1] in (0, -1)]
                        nonzero = len(undecodable) - len(cid0)
                        usable = [char for char in chars if char[0] not in (0, 0xFFFD, 32)]
                        if usable:
                            condition = "extractor_loss_recoverable_text"
                        elif undecodable and len(cid0) == len(undecodable):
                            condition = "destroyed_cid0_notdef"
                        elif undecodable:
                            condition = "undecodable_nonzero_glyph_review"
                        else:
                            condition = "source_blank"
                        result = {**row, "source_condition": condition,
                                  "character_count": len(chars),
                                  "undecodable_character_count": len(undecodable),
                                  "cid0_character_count": len(cid0),
                                  "nonzero_undecodable_glyph_count": nonzero,
                                  "diagnostic_error": ""}
                        writer.writerow(result)
                        counts[condition] += 1
            except Exception as exc:  # retain every failed diagnostic as a row
                for row in rows:
                    writer.writerow({**row, "source_condition": "diagnostic_error",
                                     "character_count": "", "undecodable_character_count": "",
                                     "cid0_character_count": "", "nonzero_undecodable_glyph_count": "",
                                     "diagnostic_error": f"{type(exc).__name__}: {exc}"})
                    counts["diagnostic_error"] += 1
            if document_index % 100 == 0 or document_index == len(grouped):
                print(f"Classified {document_index}/{len(grouped)} PDFs: {dict(counts)}", flush=True)

    qa = {"manifest_cells": len(manifest), "affected_documents": len(grouped),
          "classified_cells": sum(counts.values()), "conditions": dict(counts),
          "all_cells_classified": sum(counts.values()) == len(manifest),
          "output": str(args.output)}
    args.qa.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(qa, ensure_ascii=False, indent=2))
    return 0 if qa["all_cells_classified"] and not counts["diagnostic_error"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
