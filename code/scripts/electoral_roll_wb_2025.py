#!/usr/bin/env python3
"""Download ASDD / BLO-BLA Minutes PDFs from the CEO West Bengal SIR portal.

The target page is:
    https://ceowestbengal.wb.gov.in/asd_sir/

What this script does:
1. Reads the public district dropdown from the page HTML.
2. Calls the same JSON endpoints the site uses for AC and PS lookups.
3. Collects every available PDF URL (`asd` and/or `mom`).
4. Downloads the files into `data/raw/ceowestbengal/asd_sir/`.

Important note about the CAPTCHA
--------------------------------
The site shows a CAPTCHA modal in the browser UI, but the page source reveals
that it is generated and validated entirely in client-side JavaScript before
opening a public PDF link. This script uses the underlying public JSON endpoints
and direct PDF URLs exposed by the site itself, so no OCR or browser-based
CAPTCHA solving is needed.

Examples
--------
# Download all ASDD PDFs for one district
python code/scripts/electoral_roll_wb_2025.py --district COOCHBEHAR --doc-type asd

# Download both ASDD and MOM PDFs for all districts
python code/scripts/electoral_roll_wb_2025.py --doc-type both

# Test the workflow without downloading files
python code/scripts/electoral_roll_wb_2025.py --district 1 --max-files 10 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from pathlib import Path
from threading import Lock, current_thread
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

BASE_URL = "https://ceowestbengal.wb.gov.in/asd_sir/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    )
}
DOC_TYPE_MAP = {
    "asd": ("asd",),
    "mom": ("mom",),
    "both": ("asd", "mom"),
}


def build_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    legacy_flag = getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0)
    if legacy_flag:
        context.options |= legacy_flag
    return context


SSL_CONTEXT = build_ssl_context()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


DEFAULT_OUTPUT_ROOT = repo_root() / "data" / "raw" / "ceowestbengal" / "asd_sir"
PRINT_LOCK = Lock()


def log(message: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    worker = current_thread().name
    with PRINT_LOCK:
        print(f"[{timestamp}][{worker}] {message}", flush=True)


def fetch_text(url: str, params: Optional[Dict[str, object]] = None, timeout: int = 60) -> str:
    if params:
        joiner = "&" if "?" in url else "?"
        url = f"{url}{joiner}{urlencode(params)}"

    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch_json(url: str, params: Dict[str, object], timeout: int = 60):
    return json.loads(fetch_text(url, params=params, timeout=timeout))


def clean_whitespace(text: str) -> str:
    return " ".join(unescape(text).split())


def slugify(text: str) -> str:
    text = clean_whitespace(text).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "unknown"


def parse_districts(html: str) -> List[Dict[str, str]]:
    match = re.search(r'<select\s+id="ddlDistrict"[^>]*>(.*?)</select>', html, re.I | re.S)
    if not match:
        raise RuntimeError("Could not find the district dropdown on the target page.")

    options = re.findall(r'<option\s+value="([^"]*)"\s*>\s*(.*?)\s*</option>', match.group(1), re.I | re.S)
    districts: List[Dict[str, str]] = []

    for value, label in options:
        value = value.strip()
        label = clean_whitespace(label)
        if value:
            districts.append({"distId": value, "name": label})

    if not districts:
        raise RuntimeError("No district options were parsed from the page.")

    return districts


def filter_districts(districts: List[Dict[str, str]], district_filter: Optional[str]) -> List[Dict[str, str]]:
    if not district_filter:
        return districts

    needle = district_filter.strip().lower()
    filtered = [
        district
        for district in districts
        if district["distId"] == district_filter or needle in district["name"].lower()
    ]

    if not filtered:
        raise ValueError(f"No district matched: {district_filter!r}")

    return filtered


def collect_records_for_district(
    district: Dict[str, str],
    doc_types: Iterable[str],
    ac_filter: Optional[int],
    delay_seconds: float,
) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    dist_id = district["distId"]
    log(f"START district {dist_id} | {district['name']}")
    ac_rows = fetch_json(BASE_URL, {"handler": "AC", "distId": dist_id})
    log(f"LOOKUP district {dist_id} | {district['name']} -> {len(ac_rows)} ACs")

    for ac in ac_rows:
        ac_id = int(ac["acId"])
        ac_name = clean_whitespace(ac["name"])
        if ac_filter is not None and ac_id != ac_filter:
            continue

        ps_rows = fetch_json(BASE_URL, {"handler": "PS", "acId": ac_id})
        log(f"AC {ac_id} | {ac_name} -> {len(ps_rows)} parts")

        for row in ps_rows:
            for doc_type in doc_types:
                pdf_url = (row.get(doc_type) or "").strip()
                if not pdf_url or pdf_url == "#":
                    continue

                records.append(
                    {
                        "district_id": dist_id,
                        "district_name": district["name"],
                        "ac_id": ac_id,
                        "ac_name": ac_name,
                        "ps_id": row.get("psId"),
                        "ps_name": clean_whitespace(str(row.get("name", ""))),
                        "doc_type": doc_type,
                        "source_url": urljoin(BASE_URL, pdf_url),
                    }
                )

        if delay_seconds:
            time.sleep(delay_seconds)

    log(f"DONE district {dist_id} | {district['name']} -> {len(records)} PDF tasks")
    return records


def collect_pdf_records(
    districts: List[Dict[str, str]],
    doc_types: Iterable[str],
    ac_filter: Optional[int],
    delay_seconds: float,
    workers: int,
) -> List[Dict[str, object]]:
    if workers <= 1 or len(districts) <= 1:
        records: List[Dict[str, object]] = []
        for district in districts:
            records.extend(collect_records_for_district(district, doc_types, ac_filter, delay_seconds))
    else:
        records = []
        with ThreadPoolExecutor(max_workers=min(workers, len(districts))) as executor:
            futures = {
                executor.submit(collect_records_for_district, district, doc_types, ac_filter, delay_seconds): district
                for district in districts
            }
            for future in as_completed(futures):
                records.extend(future.result())

    records.sort(key=lambda item: (str(item["district_id"]), int(item["ac_id"]), int(item["ps_id"]), str(item["doc_type"])))
    return records


def output_path(output_root: Path, record: Dict[str, object]) -> Path:
    district_dir = f"{record['district_id']}_{slugify(str(record['district_name']))}"
    ac_dir = f"{int(record['ac_id']):03d}_{slugify(str(record['ac_name']))}"
    filename = Path(urlsplit(str(record["source_url"])).path).name or "download.pdf"
    return output_root / str(record["doc_type"]) / district_dir / ac_dir / filename


def download_file(url: str, destination: Path, overwrite: bool = False, dry_run: bool = False) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists() and not overwrite:
        return "skipped"

    if dry_run:
        return "dry-run"

    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=120, context=SSL_CONTEXT) as response:
        content = response.read()

    destination.write_bytes(content)
    return "downloaded"


def download_record(
    record: Dict[str, object],
    output_root: Path,
    overwrite: bool,
    dry_run: bool,
) -> Tuple[Dict[str, object], Path, str, str]:
    destination = output_path(output_root, record)
    try:
        status = download_file(
            url=str(record["source_url"]),
            destination=destination,
            overwrite=overwrite,
            dry_run=dry_run,
        )
        error = ""
    except Exception as exc:  # pragma: no cover - runtime/network safeguard
        status = "failed"
        error = str(exc)
    return record, destination, status, error


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download CEO West Bengal ASD/MOM PDFs into this repo.")
    parser.add_argument("--district", help="District ID or partial district name, e.g. `1` or `COOCHBEHAR`.")
    parser.add_argument("--ac", type=int, help="Optional Assembly Constituency ID filter.")
    parser.add_argument("--doc-type", choices=sorted(DOC_TYPE_MAP), default="both", help="Which PDF family to download.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help="Destination root folder.")
    parser.add_argument("--delay", type=float, default=0.15, help="Delay between AC requests in seconds.")
    parser.add_argument("--workers", type=int, default=6, help="Parallel worker count for district lookup and PDF downloads.")
    parser.add_argument("--max-files", type=int, help="Stop after this many PDF records (useful for testing).")
    parser.add_argument("--overwrite", action="store_true", help="Re-download files that already exist.")
    parser.add_argument("--dry-run", action="store_true", help="List planned downloads without fetching PDFs.")
    parser.add_argument("--list-districts", action="store_true", help="Print district IDs/names and exit.")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    try:
        homepage_html = fetch_text(BASE_URL)
        districts = parse_districts(homepage_html)
    except Exception as exc:  # pragma: no cover - runtime/network safeguard
        print(f"Failed to read the source page: {exc}", file=sys.stderr)
        return 1

    if args.list_districts:
        for district in districts:
            print(f"{district['distId']:>2}  {district['name']}")
        return 0

    try:
        selected_districts = filter_districts(districts, args.district)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    args.output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_root / "manifest.csv"
    file_exists = manifest_path.exists()

    processed = 0
    downloaded = 0
    skipped = 0
    failed = 0

    lookup_workers = min(max(1, args.workers), len(selected_districts))
    log(
        f"COLLECT phase -> {len(selected_districts)} district(s), {lookup_workers} worker(s), doc_type={args.doc_type}"
    )

    records = collect_pdf_records(
        districts=selected_districts,
        doc_types=DOC_TYPE_MAP[args.doc_type],
        ac_filter=args.ac,
        delay_seconds=args.delay,
        workers=max(1, args.workers),
    )

    if args.max_files is not None:
        records = records[: args.max_files]

    with manifest_path.open("a", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "district_id",
            "district_name",
            "ac_id",
            "ac_name",
            "ps_id",
            "ps_name",
            "doc_type",
            "source_url",
            "local_path",
            "status",
            "error",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        download_workers = min(max(1, args.workers), len(records)) if records else 1
        log(f"DOWNLOAD phase -> {len(records)} file(s) queued, {download_workers} worker(s)")

        if max(1, args.workers) == 1 or len(records) <= 1:
            result_iter = (
                download_record(record, args.output_root, args.overwrite, args.dry_run)
                for record in records
            )
        else:
            executor = ThreadPoolExecutor(max_workers=download_workers)
            future_map = {
                executor.submit(download_record, record, args.output_root, args.overwrite, args.dry_run): record
                for record in records
            }
            result_iter = (future.result() for future in as_completed(future_map))

        try:
            for processed, (record, destination, status, error) in enumerate(result_iter, start=1):
                if status == "downloaded":
                    downloaded += 1
                elif status in {"skipped", "dry-run"}:
                    skipped += 1
                else:
                    failed += 1

                try:
                    local_path = str(destination.relative_to(repo_root()))
                except ValueError:
                    local_path = str(destination)

                row = {
                    **record,
                    "local_path": local_path,
                    "status": status,
                    "error": error,
                }
                writer.writerow(row)

                log(
                    f"[{processed}] {status.upper():9} {record['doc_type']} | "
                    f"D{record['district_id']} AC{record['ac_id']} PS{record['ps_id']} -> {destination.name}"
                )
        finally:
            if 'executor' in locals():
                executor.shutdown(wait=True)

    print("\nSummary")
    print("-------")
    print(f"Processed : {processed}")
    print(f"Downloaded: {downloaded}")
    print(f"Skipped   : {skipped}")
    print(f"Failed    : {failed}")
    print(f"Manifest  : {manifest_path}")
    print(f"Output    : {args.output_root}")

    return 0 if failed == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
