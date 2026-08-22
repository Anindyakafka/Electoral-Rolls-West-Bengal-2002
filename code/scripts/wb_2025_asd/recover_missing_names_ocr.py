#!/usr/bin/env python3
"""OCR only name cells that were unreadable in the PDF text layer.

This writes an append-only recovery sidecar.  Raw extraction values are never
modified, and interrupted runs resume using the lineage key in the sidecar.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

try:
    import fitz
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyMuPDF is required: pip install pymupdf") from exc


DEFAULT_SOURCE = Path(r"E:\Electoral roll\ceowestbengal\asd_sir\asd")
DEFAULT_MANIFEST = Path("data/interim/wb_2025_asd/missing_name_cells.csv")
DEFAULT_OUTPUT = Path("data/interim/wb_2025_asd/missing_name_ocr_recovery.csv")
DEFAULT_QA = Path("data/interim/wb_2025_asd/missing_name_ocr_qa.json")
DEFAULT_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
DEFAULT_TESSDATA = Path("tools/tessdata")
NAME_COLUMN = {"elector_name_raw": 2, "relation_name_raw": 4}
KEY_FIELDS = ("document_id", "source_page", "source_table", "source_row", "missing_field")
OUTPUT_FIELDS = [
    *KEY_FIELDS,
    "source_relative_path",
    "district_id",
    "serial_number_raw",
    "epic_number_raw",
    "ocr_text",
    "ocr_mean_confidence",
    "ocr_language",
    "ocr_psm",
    "cell_bbox",
    "status",
    "error",
]


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--qa", type=Path, default=DEFAULT_QA)
    parser.add_argument("--tesseract", type=Path, default=DEFAULT_TESSERACT)
    parser.add_argument("--tessdata", type=Path, default=DEFAULT_TESSDATA)
    parser.add_argument("--dpi", type=int, default=500)
    parser.add_argument("--limit", type=int, help="Process at most N pending cells (for pilots).")
    parser.add_argument("--district", action="append", help="Only these numeric district IDs.")
    parser.add_argument("--save-crops", type=Path, help="Optional directory for cell PNGs used in QA.")
    return parser.parse_args()


def key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row[name] for name in KEY_FIELDS)


def language_for(district_id: str) -> str:
    # Darjeeling and Kalimpong reports frequently use Devanagari/Nepali.
    return "nep+hin+eng" if int(district_id) in {3, 23} else "ben+eng"


def clean_ocr(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace("\x0c", " "))
    text = re.sub(r"\s+", " ", text).strip(" |¦—_-\t\r\n")
    return text


def run_tesseract(
    executable: Path, tessdata: Path, png: bytes, language: str, psm: int
) -> tuple[str, float | None]:
    command = [
        str(executable), "stdin", "stdout", "--tessdata-dir", str(tessdata.resolve()),
        "-l", language, "--psm", str(psm), "tsv",
    ]
    process = subprocess.run(command, input=png, capture_output=True, check=False)
    if process.returncode:
        raise RuntimeError(process.stderr.decode("utf-8", errors="replace").strip())
    decoded = process.stdout.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(decoded), delimiter="\t")
    words: list[str] = []
    confidences: list[float] = []
    for item in reader:
        word = clean_ocr(item.get("text", ""))
        if not word:
            continue
        words.append(word)
        try:
            confidence = float(item.get("conf", "-1"))
            if confidence >= 0:
                confidences.append(confidence)
        except ValueError:
            pass
    text = clean_ocr(" ".join(words))
    mean = round(sum(confidences) / len(confidences), 2) if confidences else None
    return text, mean


def load_completed(path: Path) -> set[tuple[str, ...]]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {key(row) for row in csv.DictReader(handle)}


def main() -> int:
    args = arguments()
    for needed in (args.source, args.manifest, args.tesseract, args.tessdata):
        if not needed.exists():
            raise SystemExit(f"Required path not found: {needed}")
    completed = load_completed(args.output)
    selected_districts = {int(value) for value in args.district or []}
    with args.manifest.open("r", encoding="utf-8-sig", newline="") as handle:
        pending = [
            row for row in csv.DictReader(handle)
            if key(row) not in completed
            and (not selected_districts or int(row["district_id"]) in selected_districts)
        ]
    if args.limit is not None:
        pending = pending[: max(0, args.limit)]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.save_crops:
        args.save_crops.mkdir(parents=True, exist_ok=True)
    write_header = not args.output.exists() or args.output.stat().st_size == 0
    statuses: Counter[str] = Counter()
    documents: dict[Path, fitz.Document] = {}
    try:
        with args.output.open("a", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
            if write_header:
                writer.writeheader()
            for index, row in enumerate(pending, start=1):
                result = {name: row.get(name, "") for name in OUTPUT_FIELDS}
                result.update({"ocr_text": "", "ocr_mean_confidence": "", "ocr_language": "",
                               "ocr_psm": "", "cell_bbox": "", "status": "error", "error": ""})
                try:
                    pdf_path = args.source / Path(row["source_relative_path"])
                    document = documents.get(pdf_path)
                    if document is None:
                        document = fitz.open(pdf_path)
                        documents[pdf_path] = document
                    page = document[int(row["source_page"]) - 1]
                    tables = page.find_tables().tables
                    table = tables[int(row["source_table"]) - 1]
                    row_index = int(row["source_row"]) - 1
                    column_index = NAME_COLUMN[row["missing_field"]]
                    rectangle = table.cells[column_index * table.row_count + row_index]
                    if rectangle is None:
                        result["status"] = "missing_cell_geometry"
                    else:
                        cell = fitz.Rect(rectangle)
                        # Keep the full cell but exclude most ruling-line ink.
                        clip = fitz.Rect(cell.x0 + 0.6, cell.y0 + 0.6, cell.x1 - 0.6, cell.y1 - 0.6)
                        pix = page.get_pixmap(dpi=args.dpi, clip=clip, colorspace=fitz.csGRAY, alpha=False)
                        png = pix.tobytes("png")
                        language = language_for(row["district_id"])
                        text, confidence = run_tesseract(args.tesseract, args.tessdata, png, language, 7)
                        psm = 7
                        if not text:
                            text, confidence = run_tesseract(args.tesseract, args.tessdata, png, language, 6)
                            psm = 6
                        result.update({
                            "ocr_text": text,
                            "ocr_mean_confidence": "" if confidence is None else confidence,
                            "ocr_language": language,
                            "ocr_psm": psm,
                            "cell_bbox": ",".join(f"{value:.3f}" for value in cell),
                            "status": "recovered" if text else "ocr_blank",
                        })
                        if args.save_crops:
                            crop_name = "__".join(key(row)).replace("/", "_") + ".png"
                            (args.save_crops / crop_name).write_bytes(png)
                except Exception as exc:  # corpus-dependent; retain exact failure for audit
                    result["error"] = f"{type(exc).__name__}: {exc}"
                writer.writerow(result)
                handle.flush()
                statuses[result["status"]] += 1
                if index % 25 == 0 or index == len(pending):
                    print(f"OCR {index}/{len(pending)} cells: {dict(statuses)}", flush=True)
    finally:
        for document in documents.values():
            document.close()

    summary = {
        "manifest": str(args.manifest), "output": str(args.output),
        "already_completed": len(completed), "processed_this_run": len(pending),
        "status_this_run": dict(statuses), "dpi": args.dpi,
    }
    args.qa.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not statuses.get("error") else 2


if __name__ == "__main__":
    raise SystemExit(main())
