#!/usr/bin/env python3
"""Extract all WB 2025 ASD PDF tables into one lineage-preserving CSV."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

try:
    import fitz
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyMuPDF is required: pip install pymupdf") from exc

DEFAULT_SOURCE = Path(r"E:\Electoral roll\ceowestbengal\asd_sir\asd")
DEFAULT_OUTPUT = Path("data/interim/wb_2025_asd/removed_electors_raw.csv")
DEFAULT_QA = Path("data/interim/wb_2025_asd/extraction_qa.json")
FILE_RE = re.compile(r"^uncollectable_elector_report_ac(?P<ac>\d+)_part(?P<part>\d+)\.pdf$", re.I)
DIR_RE = re.compile(r"^(?P<number>\d+)_(?P<slug>.+)$")
EXPECTED_COLUMNS = 10
OUTPUT_COLUMNS = [
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
    "elector_name_raw",
    "relation_type_raw",
    "relation_name_raw",
    "old_part_number_raw",
    "old_serial_number_raw",
    "age_raw",
    "gender_raw",
    "uncollectable_reason_raw",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--qa", type=Path, default=DEFAULT_QA)
    parser.add_argument("--limit", type=int, help="Extract only the first N sorted PDFs.")
    parser.add_argument(
        "--district",
        action="append",
        help="District directory name or numeric prefix; repeat to select multiple districts.",
    )
    parser.add_argument("--workers", type=int, default=1, help="Parallel PDF workers (use 4-6 after uploads finish).")
    return parser.parse_args()


def select_paths(source: Path, districts: list[str] | None) -> list[Path]:
    paths = sorted(source.rglob("*.pdf"))
    if not districts:
        return paths
    selectors = {value.strip().lower() for value in districts if value.strip()}
    selected = []
    for path in paths:
        relative = path.relative_to(source)
        district_dir = relative.parts[0].lower()
        district_number = district_dir.split("_", 1)[0].lstrip("0") or "0"
        if district_dir in selectors or district_number in selectors:
            selected.append(path)
    return selected


def clean_cell(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.replace("\u00a0", " ").split())


def document_identity(path: Path, root: Path) -> dict[str, object]:
    relative = path.relative_to(root)
    district_match = DIR_RE.match(relative.parts[0])
    ac_match = DIR_RE.match(relative.parts[1])
    file_match = FILE_RE.match(path.name)
    if not district_match or not ac_match or not file_match:
        raise ValueError(f"Unexpected source path structure: {relative}")
    district_id = int(district_match.group("number"))
    ac_id = int(file_match.group("ac"))
    part_id = int(file_match.group("part"))
    return {
        "document_id": f"wb2025_asd_ac{ac_id:03d}_part{part_id:04d}",
        "source_relative_path": relative.as_posix(),
        "district_id": district_id,
        "district_slug": district_match.group("slug"),
        "ac_id": ac_id,
        "ac_slug": ac_match.group("slug"),
        "part_id": part_id,
    }


def is_data_row(cells: list[str]) -> bool:
    return len(cells) == EXPECTED_COLUMNS and cells[0].strip().isdigit()


def extract_cells_by_geometry(page: fitz.Page, table: object) -> list[list[str]]:
    """Read cells in geometric table order without scrambling combining marks."""
    rows: list[list[str]] = []
    row_count = int(table.row_count)
    column_count = int(table.col_count)
    cells = table.cells
    if len(cells) != row_count * column_count:
        return rows
    # Extract words once. Calling get_textbox() for every cell reparses the page
    # hundreds of times and makes a statewide run unnecessarily expensive.
    words = page.get_text("words", sort=False)
    for row_index in range(row_count):
        row = []
        for column_index in range(column_count):
            rectangle = cells[column_index * row_count + row_index]
            if rectangle is None:
                text = ""
            else:
                cell = fitz.Rect(rectangle)
                selected = [
                    word
                    for word in words
                    if cell.x0 <= (word[0] + word[2]) / 2 <= cell.x1
                    and cell.y0 <= (word[1] + word[3]) / 2 <= cell.y1
                ]
                selected.sort(key=lambda word: (word[5], word[6], word[7]))
                text = " ".join(str(word[4]) for word in selected)
            row.append(clean_cell(text))
        rows.append(row)
    return rows


def extract_document(path: Path, root: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    identity = document_identity(path, root)
    records: list[dict[str, object]] = []
    qa: dict[str, object] = {
        **identity,
        "pages": 0,
        "tables": 0,
        "records": 0,
        "non_10_column_tables": 0,
        "non_data_rows": 0,
        "error": "",
    }
    if path.stat().st_size == 0:
        qa["error"] = "zero_byte_file"
        return records, qa

    try:
        document = fitz.open(path)
        qa["pages"] = document.page_count
        for page_index, page in enumerate(document, start=1):
            tables = page.find_tables().tables
            qa["tables"] = int(qa["tables"]) + len(tables)
            for table_index, table in enumerate(tables, start=1):
                if table.col_count != EXPECTED_COLUMNS:
                    qa["non_10_column_tables"] = int(qa["non_10_column_tables"]) + 1
                    continue
                extracted = extract_cells_by_geometry(page, table)
                for source_row, raw_cells in enumerate(extracted, start=1):
                    cells = [clean_cell(cell) for cell in raw_cells]
                    if not is_data_row(cells):
                        qa["non_data_rows"] = int(qa["non_data_rows"]) + 1
                        continue
                    records.append(
                        {
                            **identity,
                            "source_page": page_index,
                            "source_table": table_index,
                            "source_row": source_row,
                            "serial_number_raw": cells[0],
                            "epic_number_raw": cells[1],
                            "elector_name_raw": cells[2],
                            "relation_type_raw": cells[3],
                            "relation_name_raw": cells[4],
                            "old_part_number_raw": cells[5],
                            "old_serial_number_raw": cells[6],
                            "age_raw": cells[7],
                            "gender_raw": cells[8],
                            "uncollectable_reason_raw": cells[9],
                        }
                    )
        document.close()
        qa["records"] = len(records)
    except Exception as exc:  # pragma: no cover - corpus-dependent
        qa["error"] = f"{type(exc).__name__}: {exc}"
    return records, qa


def extract_document_worker(arguments: tuple[str, str]) -> tuple[list[dict[str, object]], dict[str, object]]:
    path, root = arguments
    return extract_document(Path(path), Path(root))


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    if not source.is_dir():
        print(f"Source directory not found: {source}", file=sys.stderr)
        return 1

    paths = select_paths(source, args.district)
    if args.limit is not None:
        paths = paths[: max(0, args.limit)]
    if not paths:
        print("No PDFs matched the requested source/district selection.", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    qa_rows = []
    total_records = 0

    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        work = ((str(path), str(source)) for path in paths)
        if args.workers > 1:
            executor = ProcessPoolExecutor(max_workers=args.workers)
            results = executor.map(extract_document_worker, work, chunksize=4)
        else:
            executor = None
            results = map(extract_document_worker, work)
        for index, (records, qa) in enumerate(results, start=1):
            writer.writerows(records)
            total_records += len(records)
            qa_rows.append(qa)
            if index % 10 == 0 or index == len(paths):
                handle.flush()
                print(f"Extracted {index}/{len(paths)} PDFs; rows={total_records}", flush=True)
        if executor is not None:
            executor.shutdown()

    errors = Counter(str(row["error"]) for row in qa_rows if row["error"])
    summary = {
        "source": str(source),
        "output": str(args.output),
        "documents_attempted": len(paths),
        "documents_with_records": sum(int(row["records"]) > 0 for row in qa_rows),
        "documents_without_records": sum(int(row["records"]) == 0 for row in qa_rows),
        "pages": sum(int(row["pages"]) for row in qa_rows),
        "tables": sum(int(row["tables"]) for row in qa_rows),
        "records": total_records,
        "non_10_column_tables": sum(int(row["non_10_column_tables"]) for row in qa_rows),
        "non_data_rows": sum(int(row["non_data_rows"]) for row in qa_rows),
        "errors": dict(errors),
        "documents": qa_rows,
    }
    args.qa.parent.mkdir(parents=True, exist_ok=True)
    args.qa.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "documents"}, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
