#!/usr/bin/env python3
"""Build a document-level manifest and QA summary for WB 2025 ASD PDFs."""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

try:
    import fitz
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyMuPDF is required: pip install pymupdf") from exc

DEFAULT_SOURCE = Path(r"E:\Electoral roll\ceowestbengal\asd_sir\asd")
DEFAULT_MANIFEST = Path("data/metadata/wb_2025_asd/pdf_manifest.csv")
DEFAULT_SUMMARY = Path("data/metadata/wb_2025_asd/audit_summary.json")
FILE_RE = re.compile(r"^uncollectable_elector_report_ac(?P<ac>\d+)_part(?P<part>\d+)\.pdf$", re.I)
DIR_RE = re.compile(r"^(?P<number>\d+)_(?P<slug>.+)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--limit", type=int, help="Audit only the first N sorted PDFs.")
    parser.add_argument(
        "--inspect-tables",
        action="store_true",
        help="Run slow table detection on every page; row extraction also performs this QA.",
    )
    return parser.parse_args()


def script_counts(text: str) -> tuple[int, int, int]:
    bengali = sum("\u0980" <= char <= "\u09ff" for char in text)
    devanagari = sum("\u0900" <= char <= "\u097f" for char in text)
    latin = sum(char.isascii() and char.isalpha() for char in text)
    return bengali, devanagari, latin


def language_label(bengali: int, devanagari: int, latin: int) -> str:
    counts = {"bengali": bengali, "devanagari": devanagari, "latin": latin}
    label, count = max(counts.items(), key=lambda item: item[1])
    return label if count else "unknown"


def identity(path: Path, root: Path) -> dict[str, object]:
    relative = path.relative_to(root)
    parts = relative.parts
    district = DIR_RE.match(parts[0]) if len(parts) > 0 else None
    ac_dir = DIR_RE.match(parts[1]) if len(parts) > 1 else None
    filename = FILE_RE.match(path.name)
    return {
        "source_path": str(path),
        "relative_path": relative.as_posix(),
        "district_id": int(district.group("number")) if district else "",
        "district_slug": district.group("slug") if district else "",
        "ac_id_dir": int(ac_dir.group("number")) if ac_dir else "",
        "ac_slug": ac_dir.group("slug") if ac_dir else "",
        "ac_id_file": int(filename.group("ac")) if filename else "",
        "part_id": int(filename.group("part")) if filename else "",
        "filename_matches_pattern": bool(filename),
    }


def audit_one(path: Path, root: Path, inspect_tables: bool) -> dict[str, object]:
    row = identity(path, root)
    row.update(
        size_bytes=path.stat().st_size,
        pdf_open_ok=False,
        page_count="",
        text_chars="",
        image_count="",
        table_pages="",
        language="unknown",
        encrypted="",
        error="",
    )
    if path.stat().st_size == 0:
        row["error"] = "zero_byte_file"
        return row

    try:
        document = fitz.open(path)
        row["pdf_open_ok"] = True
        row["page_count"] = document.page_count
        row["encrypted"] = bool(document.needs_pass)
        text_chars = image_count = table_pages = 0
        bengali = devanagari = latin = 0
        for page in document:
            text = page.get_text()
            text_chars += len(text)
            image_count += len(page.get_images(full=True))
            b_count, d_count, l_count = script_counts(text)
            bengali += b_count
            devanagari += d_count
            latin += l_count
            if inspect_tables:
                try:
                    table_pages += int(bool(page.find_tables().tables))
                except Exception:
                    pass
        document.close()
        row["text_chars"] = text_chars
        row["image_count"] = image_count
        row["table_pages"] = table_pages
        row["language"] = language_label(bengali, devanagari, latin)
    except Exception as exc:  # pragma: no cover - corpus-dependent
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def summarize(rows: list[dict[str, object]], source: Path, inspect_tables: bool) -> dict[str, object]:
    valid_pages = [int(row["page_count"]) for row in rows if row["page_count"] != ""]
    language_counts = Counter(str(row["language"]) for row in rows)
    errors = Counter(str(row["error"]) for row in rows if row["error"])
    ac_mismatch = sum(
        row["ac_id_dir"] != row["ac_id_file"]
        for row in rows
        if row["ac_id_dir"] != "" and row["ac_id_file"] != ""
    )
    return {
        "source": str(source),
        "documents": len(rows),
        "bytes": sum(int(row["size_bytes"]) for row in rows),
        "openable_documents": sum(bool(row["pdf_open_ok"]) for row in rows),
        "zero_byte_documents": sum(int(row["size_bytes"]) == 0 for row in rows),
        "documents_without_text": sum(
            row["pdf_open_ok"] and int(row["text_chars"] or 0) == 0 for row in rows
        ),
        "documents_with_images": sum(int(row["image_count"] or 0) > 0 for row in rows),
        "table_inspection_enabled": inspect_tables,
        "documents_with_all_pages_tabled": (
            sum(row["page_count"] != "" and row["page_count"] == row["table_pages"] for row in rows)
            if inspect_tables
            else None
        ),
        "pages": sum(valid_pages),
        "page_count_min": min(valid_pages, default=None),
        "page_count_median": statistics.median(valid_pages) if valid_pages else None,
        "page_count_max": max(valid_pages, default=None),
        "language_counts": dict(sorted(language_counts.items())),
        "filename_pattern_failures": sum(not row["filename_matches_pattern"] for row in rows),
        "ac_directory_filename_mismatches": ac_mismatch,
        "errors": dict(errors),
    }


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    if not source.is_dir():
        print(f"Source directory not found: {source}", file=sys.stderr)
        return 1

    paths = sorted(source.rglob("*.pdf"))
    if args.limit is not None:
        paths = paths[: max(0, args.limit)]
    rows = []
    for index, path in enumerate(paths, start=1):
        rows.append(audit_one(path, source, args.inspect_tables))
        if index % 1000 == 0:
            print(f"Audited {index}/{len(paths)} PDFs", flush=True)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with args.manifest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            writer.writerows(rows)

    summary = summarize(rows, source, args.inspect_tables)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
