#!/usr/bin/env python3
"""Retry failed downloads listed in the scraper manifest.

Default manifest path:
    D:\\Electoral roll\\ceowestbengal\\asd_sir\\manifest.csv

This script:
1. Reads manifest rows in order.
2. Keeps only the latest status per target file path.
3. Retries entries whose latest status is `failed`.
4. Writes files to their manifest `local_path` locations.
5. Appends new status rows back into the same manifest.
"""

from __future__ import annotations

import argparse
import csv
import ssl
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock, current_thread
from typing import Dict, List, Tuple
from urllib.request import Request, urlopen

DEFAULT_MANIFEST = Path(r"D:\Electoral roll\ceowestbengal\asd_sir\manifest.csv")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    )
}
PRINT_LOCK = Lock()


def build_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    legacy_flag = getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0)
    if legacy_flag:
        context.options |= legacy_flag
    return context


SSL_CONTEXT = build_ssl_context()


def log(message: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    worker = current_thread().name
    with PRINT_LOCK:
        print(f"[{timestamp}][{worker}] {message}", flush=True)


def normalize_status(value: str) -> str:
    return (value or "").strip().lower()


def get_retry_candidates(
    manifest_path: Path,
    doc_type: str,
) -> Tuple[List[Dict[str, str]], List[str]]:
    with manifest_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        latest_by_path: Dict[str, Dict[str, str]] = {}

        for row in reader:
            local_path = (row.get("local_path") or "").strip()
            if not local_path:
                continue
            latest_by_path[local_path] = row

    candidates = [
        row
        for row in latest_by_path.values()
        if normalize_status(row.get("status", "")) == "failed"
        and (doc_type == "both" or (row.get("doc_type") or "").strip().lower() == doc_type)
    ]
    candidates.sort(
        key=lambda r: (
            int((r.get("district_id") or "0") or 0),
            int((r.get("ac_id") or "0") or 0),
            int((r.get("ps_id") or "0") or 0),
            (r.get("doc_type") or ""),
        )
    )

    if not fieldnames:
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

    return candidates, fieldnames


def to_destination(local_path: str, manifest_path: Path) -> Path:
    p = Path(local_path)
    if p.is_absolute():
        return p
    return manifest_path.parent / p


def retry_one(
    row: Dict[str, str],
    manifest_path: Path,
    timeout: int,
    dry_run: bool,
) -> Tuple[Dict[str, str], str, str]:
    source_url = (row.get("source_url") or "").strip()
    destination = to_destination((row.get("local_path") or "").strip(), manifest_path)

    if not source_url:
        return row, "failed", "Missing source_url in manifest row"

    if destination.exists():
        return row, "downloaded", "Already exists"

    if dry_run:
        return row, "dry-run", ""

    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        request = Request(source_url, headers=HEADERS)
        with urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:
            content = response.read()
        destination.write_bytes(content)
        return row, "downloaded", ""
    except Exception as exc:  # pragma: no cover - runtime/network safeguard
        return row, "failed", str(exc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Retry failed rows from the electoral-roll manifest.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to manifest CSV.")
    parser.add_argument("--workers", type=int, default=8, help="Parallel download workers.")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--doc-type",
        choices=["asd", "mom", "both"],
        default="both",
        help="Retry failures for only one document family.",
    )
    parser.add_argument("--max-retries", type=int, help="Retry only the first N failed entries.")
    parser.add_argument("--dry-run", action="store_true", help="Do not download files; only simulate retries.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    manifest_path = args.manifest

    if not manifest_path.exists():
        log(f"Manifest not found: {manifest_path}")
        return 1

    candidates, fieldnames = get_retry_candidates(manifest_path, args.doc_type)
    if args.max_retries is not None:
        candidates = candidates[: args.max_retries]

    log(
        f"Found {len(candidates)} failed latest entries in {manifest_path} "
        f"for doc_type={args.doc_type}"
    )
    if not candidates:
        log("Nothing to retry.")
        return 0

    downloaded = 0
    failed = 0
    dry = 0

    with manifest_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {
                executor.submit(retry_one, row, manifest_path, args.timeout, args.dry_run): row for row in candidates
            }

            for i, future in enumerate(as_completed(futures), start=1):
                row, status, error = future.result()
                updated = dict(row)
                updated["status"] = status
                updated["error"] = error
                writer.writerow(updated)

                if status == "downloaded":
                    downloaded += 1
                elif status == "dry-run":
                    dry += 1
                else:
                    failed += 1

                log(
                    f"[{i}/{len(candidates)}] {status.upper():9} "
                    f"D{row.get('district_id')} AC{row.get('ac_id')} PS{row.get('ps_id')} -> "
                    f"{Path((row.get('local_path') or '')).name}"
                )

    log("Retry Summary")
    log(f"Downloaded: {downloaded}")
    log(f"Dry-run   : {dry}")
    log(f"Failed    : {failed}")
    log(f"Manifest  : {manifest_path}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
