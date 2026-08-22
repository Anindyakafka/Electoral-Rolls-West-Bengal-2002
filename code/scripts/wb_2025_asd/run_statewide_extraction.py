#!/usr/bin/env python3
"""Run resumable district shards and combine them into one statewide ASD CSV."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_SOURCE = Path(r"E:\Electoral roll\ceowestbengal\asd_sir\asd")
DEFAULT_SHARDS = Path("data/interim/wb_2025_asd/shards")
DEFAULT_OUTPUT = Path("data/interim/wb_2025_asd/removed_electors_raw.csv")
DEFAULT_SUMMARY = Path("data/interim/wb_2025_asd/statewide_extraction_qa.json")
ALLOWED_SOURCE_ERRORS = {"zero_byte_file"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--shards-dir", type=Path, default=DEFAULT_SHARDS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--workers", type=int, default=1, help="Workers inside each district shard.")
    parser.add_argument("--force", action="store_true", help="Rebuild shards whose QA already passes.")
    return parser.parse_args()


def expected_pdf_count(district_dir: Path) -> int:
    return sum(1 for _ in district_dir.rglob("*.pdf"))


def load_qa(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def acceptable_errors(qa: dict) -> bool:
    errors = qa.get("errors") or {}
    return set(errors).issubset(ALLOWED_SOURCE_ERRORS)


def shard_is_complete(csv_path: Path, qa_path: Path, expected: int) -> bool:
    qa = load_qa(qa_path)
    return bool(
        csv_path.is_file()
        and csv_path.stat().st_size > 0
        and qa
        and int(qa.get("documents_attempted", -1)) == expected
        and acceptable_errors(qa)
    )


def run_shard(
    extractor: Path,
    source: Path,
    district_dir: Path,
    shards_dir: Path,
    workers: int,
) -> tuple[Path, Path, int]:
    district_name = district_dir.name
    csv_path = shards_dir / f"{district_name}.csv"
    qa_path = shards_dir / f"{district_name}_qa.json"
    command = [
        sys.executable,
        str(extractor),
        "--source",
        str(source),
        "--district",
        district_name,
        "--output",
        str(csv_path),
        "--qa",
        str(qa_path),
        "--workers",
        str(workers),
    ]
    print(f"START {district_name}", flush=True)
    completed = subprocess.run(command, check=False)
    return csv_path, qa_path, completed.returncode


def combine_shards(shards: list[Path], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    total_rows = 0
    expected_header: list[str] | None = None
    with output.open("w", encoding="utf-8-sig", newline="") as target:
        writer = None
        for shard in shards:
            with shard.open("r", encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source)
                header = list(reader.fieldnames or [])
                if expected_header is None:
                    expected_header = header
                    writer = csv.DictWriter(target, fieldnames=expected_header)
                    writer.writeheader()
                elif header != expected_header:
                    raise RuntimeError(f"Shard schema mismatch: {shard}")
                assert writer is not None
                for row in reader:
                    writer.writerow(row)
                    total_rows += 1
    return total_rows


def main() -> int:
    args = parse_args()
    started = time.time()
    source = args.source.resolve()
    if not source.is_dir():
        print(f"Source directory not found: {source}", file=sys.stderr)
        return 1
    if args.workers < 1:
        print("--workers must be positive", file=sys.stderr)
        return 2

    extractor = Path(__file__).with_name("extract_removed_electors.py").resolve()
    args.shards_dir.mkdir(parents=True, exist_ok=True)
    district_dirs = sorted(path for path in source.iterdir() if path.is_dir())
    run_rows = []
    completed_shards = []

    for district_dir in district_dirs:
        expected = expected_pdf_count(district_dir)
        csv_path = args.shards_dir / f"{district_dir.name}.csv"
        qa_path = args.shards_dir / f"{district_dir.name}_qa.json"
        if not args.force and shard_is_complete(csv_path, qa_path, expected):
            qa = load_qa(qa_path) or {}
            print(f"SKIP  {district_dir.name}: complete ({expected} PDFs, {qa.get('records', 0)} rows)", flush=True)
            returncode = 0
        else:
            csv_path, qa_path, returncode = run_shard(
                extractor, source, district_dir, args.shards_dir, args.workers
            )

        qa = load_qa(qa_path) or {}
        complete = shard_is_complete(csv_path, qa_path, expected)
        run_rows.append(
            {
                "district": district_dir.name,
                "expected_pdfs": expected,
                "attempted_pdfs": qa.get("documents_attempted"),
                "records": qa.get("records"),
                "errors": qa.get("errors", {}),
                "returncode": returncode,
                "complete": complete,
            }
        )
        if not complete:
            print(f"STOP: shard did not pass completeness checks: {district_dir.name}", file=sys.stderr)
            break
        completed_shards.append(csv_path)

    all_complete = len(completed_shards) == len(district_dirs)
    total_rows = None
    if all_complete:
        total_rows = combine_shards(completed_shards, args.output)
        print(f"COMBINED {len(completed_shards)} shards -> {args.output} ({total_rows} rows)", flush=True)
        validator = Path(__file__).with_name("validate_statewide_dataset.py").resolve()
        validation = subprocess.run(
            [
                sys.executable,
                str(validator),
                "--source",
                str(source),
                "--input",
                str(args.output),
                "--shards-dir",
                str(args.shards_dir),
            ],
            check=False,
        )
        if validation.returncode != 0:
            all_complete = False
            print("Statewide validation failed; see statewide_validation.json", file=sys.stderr)

    summary = {
        "source": str(source),
        "districts_expected": len(district_dirs),
        "districts_complete": len(completed_shards),
        "all_districts_complete": all_complete,
        "combined_output": str(args.output) if all_complete else None,
        "combined_rows": total_rows,
        "elapsed_seconds": round(time.time() - started, 1),
        "districts": run_rows,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "districts"}, indent=2))
    return 0 if all_complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
