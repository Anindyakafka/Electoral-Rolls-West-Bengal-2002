#!/usr/bin/env python3
"""Validate the combined WB 2025 ASD dataset against source and shard QA."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

try:
    import fitz
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyMuPDF is required: pip install pymupdf") from exc

DEFAULT_SOURCE = Path(r"E:\Electoral roll\ceowestbengal\asd_sir\asd")
DEFAULT_INPUT = Path("data/interim/wb_2025_asd/removed_electors_raw.csv")
DEFAULT_SHARDS = Path("data/interim/wb_2025_asd/shards")
DEFAULT_REPORT = Path("data/interim/wb_2025_asd/statewide_validation.json")
EXPECTED_COLUMNS = [
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
ALLOWED_SOURCE_ERRORS = {"zero_byte_file"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--shards-dir", type=Path, default=DEFAULT_SHARDS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def load_shard_qa(shards_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(shards_dir.glob("*_qa.json")):
        if path.name.startswith("_"):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["qa_path"] = str(path)
        rows.append(payload)
    return rows


def diagnose_missing_cells(source_root: Path, missing_cells: list[dict]) -> tuple[Counter, list[dict]]:
    outcomes: Counter = Counter()
    problem_examples: list[dict] = []
    by_document: dict[str, list[dict]] = {}
    for item in missing_cells:
        by_document.setdefault(item["source_relative_path"], []).append(item)

    for relative_path, items in by_document.items():
        try:
            document = fitz.open(source_root / relative_path)
            tables_by_page: dict[int, list] = {}
            words_by_page: dict[int, list] = {}
            for item in items:
                page_index = int(item["source_page"]) - 1
                page = document[page_index]
                if page_index not in tables_by_page:
                    tables_by_page[page_index] = page.find_tables().tables
                    words_by_page[page_index] = page.get_text("words")
                tables = tables_by_page[page_index]
                table = tables[int(item["source_table"]) - 1]
                row_index = int(item["source_row"]) - 1
                column_index = int(item["column_index"])
                rectangle = table.cells[column_index * table.row_count + row_index]
                if rectangle is None:
                    raw = ""
                else:
                    cell = fitz.Rect(rectangle)
                    raw = " ".join(
                        word[4]
                        for word in words_by_page[page_index]
                        if cell.x0 <= (word[0] + word[2]) / 2 < cell.x1
                        and cell.y0 <= (word[1] + word[3]) / 2 < cell.y1
                    )
                textbox_raw = "" if rectangle is None else page.get_textbox(cell)
                if (
                    "\x00" in raw
                    or "\ufffd" in raw
                    or "\x00" in textbox_raw
                    or "\ufffd" in textbox_raw
                ):
                    outcome = f"{item['field']}_source_undecodable"
                elif not raw.strip():
                    outcome = f"{item['field']}_source_blank"
                else:
                    outcome = f"{item['field']}_extractor_loss"
                outcomes[outcome] += 1
                if outcome.endswith("_extractor_loss"):
                    problem_examples.append({**item, "source_text": raw.strip()})
            document.close()
        except Exception as exc:
            for item in items:
                outcome = f"{item['field']}_diagnostic_failure"
                outcomes[outcome] += 1
                problem_examples.append({**item, "diagnostic_error": repr(exc)})
    return outcomes, problem_examples


def validate_rows(input_path: Path, source_root: Path | None = None) -> dict:
    result = {
        "rows": 0,
        "documents_in_csv": 0,
        "duplicate_document_serial_keys": 0,
        "documents_reappearing_noncontiguously": 0,
        "documents_with_serial_gaps": 0,
        "nonnumeric_serial_number": 0,
        "missing_epic": 0,
        "missing_elector_name": 0,
        "missing_relation_name": 0,
        "nonnumeric_age": 0,
        "nonnumeric_old_part": 0,
        "nonnumeric_old_serial": 0,
        "age_below_18": 0,
        "age_above_120": 0,
        "age_min": None,
        "age_max": None,
    }
    gender = Counter()
    reason = Counter()
    relation_type = Counter()
    seen_documents: set[str] = set()
    current_document = None
    current_serials: set[int] = set()
    missing_cells: list[dict] = []

    def close_document() -> None:
        if not current_serials:
            return
        expected = set(range(1, max(current_serials) + 1))
        if current_serials != expected:
            result["documents_with_serial_gaps"] += 1

    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        result["schema_matches"] = header == EXPECTED_COLUMNS
        result["actual_columns"] = header
        for row in reader:
            result["rows"] += 1
            document_id = row["document_id"].strip()
            if document_id != current_document:
                close_document()
                if document_id in seen_documents:
                    result["documents_reappearing_noncontiguously"] += 1
                else:
                    seen_documents.add(document_id)
                current_document = document_id
                current_serials = set()

            serial_text = row["serial_number_raw"].strip()
            if serial_text.isdigit():
                serial = int(serial_text)
                if serial in current_serials:
                    result["duplicate_document_serial_keys"] += 1
                current_serials.add(serial)
            else:
                result["nonnumeric_serial_number"] += 1

            if not row["epic_number_raw"].strip():
                result["missing_epic"] += 1
            if not row["elector_name_raw"].strip():
                result["missing_elector_name"] += 1
                missing_cells.append(
                    {
                        "field": "elector_name",
                        "column_index": 2,
                        "source_relative_path": row["source_relative_path"],
                        "source_page": row["source_page"],
                        "source_table": row["source_table"],
                        "source_row": row["source_row"],
                    }
                )
            if not row["relation_name_raw"].strip():
                result["missing_relation_name"] += 1
                missing_cells.append(
                    {
                        "field": "relation_name",
                        "column_index": 4,
                        "source_relative_path": row["source_relative_path"],
                        "source_page": row["source_page"],
                        "source_table": row["source_table"],
                        "source_row": row["source_row"],
                    }
                )

            age_text = row["age_raw"].strip()
            if age_text.isdigit():
                age = int(age_text)
                result["age_min"] = age if result["age_min"] is None else min(result["age_min"], age)
                result["age_max"] = age if result["age_max"] is None else max(result["age_max"], age)
                result["age_below_18"] += age < 18
                result["age_above_120"] += age > 120
            else:
                result["nonnumeric_age"] += 1
            result["nonnumeric_old_part"] += not row["old_part_number_raw"].strip().isdigit()
            result["nonnumeric_old_serial"] += not row["old_serial_number_raw"].strip().isdigit()
            gender[row["gender_raw"].strip()] += 1
            reason[row["uncollectable_reason_raw"].strip()] += 1
            relation_type[row["relation_type_raw"].strip()] += 1

            if result["rows"] % 500_000 == 0:
                print(f"Validated {result['rows']:,} rows", flush=True)

    close_document()
    result["documents_in_csv"] = len(seen_documents)
    result["gender_counts"] = dict(gender.most_common())
    result["reason_counts"] = dict(reason.most_common())
    result["relation_type_counts"] = dict(relation_type.most_common())
    if source_root is not None:
        diagnostics, problem_examples = diagnose_missing_cells(source_root, missing_cells)
        result["missing_text_diagnostics"] = dict(diagnostics)
        result["missing_text_problem_examples"] = problem_examples
    return result


def main() -> int:
    args = parse_args()
    if not args.source.is_dir() or not args.input.is_file():
        print("Source directory or combined input is missing.", file=sys.stderr)
        return 1

    district_dirs = sorted(path for path in args.source.iterdir() if path.is_dir())
    source_pdfs = sum(1 for _ in args.source.rglob("*.pdf"))
    shard_qa = load_shard_qa(args.shards_dir)
    shard_errors = Counter()
    for qa in shard_qa:
        shard_errors.update(qa.get("errors") or {})

    row_qa = validate_rows(args.input, args.source)
    shard_attempted = sum(int(qa.get("documents_attempted", 0)) for qa in shard_qa)
    shard_records = sum(int(qa.get("records", 0)) for qa in shard_qa)
    hard_failures = []
    checks = {
        "all_district_qa_present": len(shard_qa) == len(district_dirs),
        "source_pdf_count_matches_shards": source_pdfs == shard_attempted,
        "combined_row_count_matches_shards": row_qa["rows"] == shard_records,
        "schema_matches": bool(row_qa["schema_matches"]),
        "unique_document_serial_keys": row_qa["duplicate_document_serial_keys"] == 0,
        "documents_are_contiguous": row_qa["documents_reappearing_noncontiguously"] == 0,
        "serial_numbers_are_complete": (
            row_qa["nonnumeric_serial_number"] == 0
            and row_qa["documents_with_serial_gaps"] == 0
        ),
        "all_epics_present": row_qa["missing_epic"] == 0,
        "no_unexplained_missing_text": (
            row_qa.get("missing_text_diagnostics", {}).get("elector_name_extractor_loss", 0) == 0
            and row_qa.get("missing_text_diagnostics", {}).get("relation_name_extractor_loss", 0) == 0
            and row_qa.get("missing_text_diagnostics", {}).get("elector_name_diagnostic_failure", 0) == 0
            and row_qa.get("missing_text_diagnostics", {}).get("relation_name_diagnostic_failure", 0) == 0
        ),
        "numeric_analysis_fields": (
            row_qa["nonnumeric_serial_number"] == 0
            and row_qa["nonnumeric_age"] == 0
            and row_qa["nonnumeric_old_part"] == 0
            and row_qa["nonnumeric_old_serial"] == 0
        ),
        "only_documented_source_errors": set(shard_errors).issubset(ALLOWED_SOURCE_ERRORS),
    }
    hard_failures.extend(name for name, passed in checks.items() if not passed)
    report = {
        "source": str(args.source.resolve()),
        "combined_input": str(args.input.resolve()),
        "source_districts": len(district_dirs),
        "source_pdfs": source_pdfs,
        "shard_qa_files": len(shard_qa),
        "shard_documents_attempted": shard_attempted,
        "shard_records": shard_records,
        "source_errors": dict(shard_errors),
        "checks": checks,
        "hard_failures": hard_failures,
        "row_qa": row_qa,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "row_qa"}, indent=2))
    return 0 if not hard_failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
