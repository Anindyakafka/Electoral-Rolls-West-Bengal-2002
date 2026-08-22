"""Build a row-level manifest of blank elector/relation names needing OCR.

The manifest is deliberately separate from the raw extraction.  It identifies
the exact PDF row requiring recovery while preserving the original values and
lineage fields needed to locate the source table cell.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


NAME_FIELDS = ("elector_name_raw", "relation_name_raw")
LINEAGE_FIELDS = (
    "document_id",
    "source_relative_path",
    "source_page",
    "source_table",
    "source_row",
    "district_id",
    "district_slug",
    "ac_id",
    "ac_slug",
    "part_id",
    "serial_number_raw",
    "epic_number_raw",
)


def blank(value: str | None) -> bool:
    return value is None or not value.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/interim/wb_2025_asd/removed_electors_raw.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/interim/wb_2025_asd/missing_name_cells.csv"),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("data/interim/wb_2025_asd/missing_name_cells_summary.json"),
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    counts_by_field: Counter[str] = Counter()
    counts_by_district: Counter[str] = Counter()
    documents: set[str] = set()
    rows_with_any_missing = 0

    output_fields = [*LINEAGE_FIELDS, "missing_field", *NAME_FIELDS]
    with args.input.open("r", encoding="utf-8-sig", newline="") as source, args.output.open(
        "w", encoding="utf-8-sig", newline=""
    ) as target:
        reader = csv.DictReader(source)
        missing_columns = set((*LINEAGE_FIELDS, *NAME_FIELDS)) - set(reader.fieldnames or ())
        if missing_columns:
            raise SystemExit(f"Input is missing columns: {sorted(missing_columns)}")
        writer = csv.DictWriter(target, fieldnames=output_fields)
        writer.writeheader()
        for row in reader:
            missing = [field for field in NAME_FIELDS if blank(row[field])]
            if not missing:
                continue
            rows_with_any_missing += 1
            documents.add(row["document_id"])
            for field in missing:
                writer.writerow(
                    {**{name: row[name] for name in LINEAGE_FIELDS}, "missing_field": field,
                     **{name: row[name] for name in NAME_FIELDS}}
                )
                counts_by_field[field] += 1
                counts_by_district[f'{row["district_id"]}_{row["district_slug"]}'] += 1

    summary = {
        "input": str(args.input),
        "manifest": str(args.output),
        "missing_cells": sum(counts_by_field.values()),
        "rows_with_any_missing_name": rows_with_any_missing,
        "affected_documents": len(documents),
        "counts_by_field": dict(sorted(counts_by_field.items())),
        "counts_by_district": dict(sorted(counts_by_district.items())),
    }
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
