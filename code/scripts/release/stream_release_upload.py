#!/usr/bin/env python3
"""Stream large datasets to GitHub Releases with minimal local disk usage.

Workflow per part:
1. Build one zip part in temp storage.
2. Upload it to a GitHub Release asset.
3. Delete the local zip immediately.

This keeps local usage bounded to roughly one part size.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence
from urllib import error, parse, request
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


@dataclass(frozen=True)
class FileEntry:
    source: Path
    relative: Path
    size_bytes: int


@dataclass(frozen=True)
class SourceSpec:
    name: str
    path: Path


def parse_source(value: str) -> SourceSpec:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Source must be in NAME=PATH format.")
    name, raw_path = value.split("=", 1)
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError("Source NAME cannot be empty.")
    path = Path(raw_path.strip())
    if not raw_path.strip():
        raise argparse.ArgumentTypeError("Source PATH cannot be empty.")
    return SourceSpec(name=name, path=path)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "dataset"


def collect_files(source_dir: Path, preserve_root_folder: bool) -> List[FileEntry]:
    entries: List[FileEntry] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source_dir)
        if preserve_root_folder:
            relative = Path(source_dir.name) / relative
        entries.append(FileEntry(source=path, relative=relative, size_bytes=path.stat().st_size))
    return entries


def chunk_files(entries: Sequence[FileEntry], max_part_bytes: int) -> List[List[FileEntry]]:
    chunks: List[List[FileEntry]] = []
    current_chunk: List[FileEntry] = []
    current_size = 0

    for entry in entries:
        if current_chunk and current_size + entry.size_bytes > max_part_bytes:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0

        current_chunk.append(entry)
        current_size += entry.size_bytes

        if entry.size_bytes > max_part_bytes:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def compression_mode(name: str) -> int:
    return ZIP_DEFLATED if name == "deflated" else ZIP_STORED


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def api_request(
    method: str,
    url: str,
    token: str,
    json_body: Dict | None = None,
    data: bytes | None = None,
    content_type: str = "application/json",
) -> Dict | List | None:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif data is not None:
        body = data
        headers["Content-Type"] = content_type

    req = request.Request(url=url, method=method, data=body, headers=headers)
    try:
        with request.urlopen(req, timeout=300) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API error {exc.code} for {method} {url}: {detail}") from exc


def get_or_create_release(owner: str, repo: str, tag: str, token: str) -> Dict:
    base = f"https://api.github.com/repos/{owner}/{repo}"
    tag_url = f"{base}/releases/tags/{parse.quote(tag)}"
    try:
        release = api_request("GET", tag_url, token)
        if isinstance(release, dict):
            return release
        raise RuntimeError("Unexpected release response format")
    except RuntimeError as exc:
        if "error 404" not in str(exc):
            raise

    create_url = f"{base}/releases"
    payload = {
        "tag_name": tag,
        "name": tag,
        "draft": False,
        "prerelease": False,
        "generate_release_notes": True,
    }
    created = api_request("POST", create_url, token, json_body=payload)
    if isinstance(created, dict):
        return created
    raise RuntimeError("Unexpected create release response format")


def update_release_body(owner: str, repo: str, release_id: int, tag: str, body: str, token: str) -> Dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/{release_id}"
    payload = {
        "tag_name": tag,
        "name": tag,
        "body": body,
        "draft": False,
        "prerelease": False,
    }
    updated = api_request("PATCH", url, token, json_body=payload)
    if isinstance(updated, dict):
        return updated
    raise RuntimeError("Unexpected update release response format")


def list_release_assets(owner: str, repo: str, release_id: int, token: str) -> List[Dict]:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/{release_id}/assets?per_page=100"
    result = api_request("GET", url, token)
    return result if isinstance(result, list) else []


def delete_release_asset(owner: str, repo: str, asset_id: int, token: str) -> None:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{asset_id}"
    api_request("DELETE", url, token)


def upload_asset(
    owner: str,
    repo: str,
    release_id: int,
    token: str,
    asset_path: Path,
    asset_name: str,
    content_type: str = "application/octet-stream",
) -> Dict:
    url = (
        f"https://uploads.github.com/repos/{owner}/{repo}/releases/{release_id}/assets"
        f"?name={parse.quote(asset_name)}"
    )
    parsed = parse.urlparse(url)
    path_with_query = parsed.path + (f"?{parsed.query}" if parsed.query else "")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": content_type,
        "Content-Length": str(asset_path.stat().st_size),
    }

    conn = http.client.HTTPSConnection(parsed.netloc, timeout=300)
    try:
        conn.putrequest("POST", path_with_query)
        for key, value in headers.items():
            conn.putheader(key, value)
        conn.endheaders()

        with asset_path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                conn.send(chunk)

        response = conn.getresponse()
        payload = response.read().decode("utf-8", errors="replace")
        if response.status >= 300:
            raise RuntimeError(f"Upload failed {response.status}: {payload}")

        parsed_payload = json.loads(payload)
        if isinstance(parsed_payload, dict):
            return parsed_payload
        raise RuntimeError("Unexpected upload response format")
    finally:
        conn.close()


def build_zip_part(zip_path: Path, part_entries: Sequence[FileEntry], compress: int) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path, mode="w", compression=compress, allowZip64=True) as archive:
        for entry in part_entries:
            archive.write(entry.source, arcname=entry.relative.as_posix())


def sync_release_asset(
    owner: str,
    repo: str,
    release_id: int,
    token: str,
    asset_path: Path,
    asset_name: str,
    assets_by_name: Dict[str, Dict],
    *,
    clobber: bool,
    content_type: str,
) -> None:
    existing = assets_by_name.get(asset_name)
    if existing and not clobber:
        print(f"    skip upload (already exists): {asset_name}")
        return

    if existing:
        delete_release_asset(owner, repo, int(existing["id"]), token)
        assets_by_name.pop(asset_name, None)

    uploaded = upload_asset(
        owner,
        repo,
        release_id,
        token,
        asset_path,
        asset_name,
        content_type=content_type,
    )
    assets_by_name[asset_name] = uploaded


def parse_repo(value: str) -> tuple[str, str]:
    if "/" not in value:
        raise argparse.ArgumentTypeError("--repo must be in OWNER/REPO format")
    owner, repo = value.split("/", 1)
    owner, repo = owner.strip(), repo.strip()
    if not owner or not repo:
        raise argparse.ArgumentTypeError("--repo must be in OWNER/REPO format")
    return owner, repo


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream zip parts to GitHub Releases and delete local parts.")
    parser.add_argument("--repo", required=True, type=parse_repo, help="Target GitHub repository in OWNER/REPO form.")
    parser.add_argument("--tag", required=True, help="Release tag to create or reuse.")
    parser.add_argument("--source", action="append", type=parse_source, required=True, help="NAME=PATH; repeatable.")
    parser.add_argument("--max-part-size-gb", type=float, default=1.8)
    parser.add_argument("--compression", choices=["stored", "deflated"], default="stored")
    parser.add_argument("--temp-dir", type=Path, default=Path(r"D:\release_stream_temp"))
    parser.add_argument("--metadata-dir", type=Path, default=Path("data") / "release_assets_stream")
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--preserve-root-folder", action="store_true", default=True)
    parser.add_argument("--no-preserve-root-folder", dest="preserve_root_folder", action="store_false")
    parser.add_argument("--clobber", action="store_true", help="Replace asset if it already exists.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    owner, repo = args.repo
    max_part_bytes = int(args.max_part_size_gb * (1024 ** 3))
    if max_part_bytes <= 0:
        print("max part size must be greater than zero", file=sys.stderr)
        return 2

    token = os.environ.get(args.token_env, "").strip()
    if not token and not args.dry_run:
        print(f"Missing token in environment variable: {args.token_env}", file=sys.stderr)
        return 2

    args.temp_dir.mkdir(parents=True, exist_ok=True)
    args.metadata_dir.mkdir(parents=True, exist_ok=True)

    release = None
    release_id = 0
    assets_by_name: Dict[str, Dict] = {}
    if not args.dry_run:
        release = get_or_create_release(owner, repo, args.tag, token)
        release_id = int(release["id"])
        for asset in list_release_assets(owner, repo, release_id, token):
            if isinstance(asset, dict) and "name" in asset:
                assets_by_name[str(asset["name"])] = asset

    checksums_path = args.metadata_dir / f"{args.tag}_sha256sums.txt"
    notes_path = args.metadata_dir / f"{args.tag}_notes.md"

    with checksums_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("")

    summary_lines = [f"# Stream Upload Summary: {args.tag}", ""]
    compress = compression_mode(args.compression)

    for spec in args.source:
        if not spec.path.exists() or not spec.path.is_dir():
            print(f"Source not found: {spec.path}", file=sys.stderr)
            return 1

        entries = collect_files(spec.path, args.preserve_root_folder)
        chunks = chunk_files(entries, max_part_bytes)
        dataset_slug = slugify(spec.name)
        digits = max(3, int(math.log10(max(1, len(chunks)))) + 1)
        planned_asset_names = {
            f"{dataset_slug}_part{idx:0{digits}d}.zip"
            for idx in range(1, len(chunks) + 1)
        }

        if not args.dry_run and args.clobber:
            stale_asset_names = [
                asset_name
                for asset_name in list(assets_by_name)
                if asset_name.startswith(f"{dataset_slug}_part")
                and asset_name.endswith(".zip")
                and asset_name not in planned_asset_names
            ]
            for asset_name in stale_asset_names:
                delete_release_asset(owner, repo, int(assets_by_name[asset_name]["id"]), token)
                assets_by_name.pop(asset_name, None)
                print(f"    removed stale release asset: {asset_name}")

        summary_lines.append(f"## {spec.name}")
        summary_lines.append(f"- Source: {spec.path}")
        summary_lines.append(f"- Files: {len(entries)}")
        summary_lines.append(f"- Parts: {len(chunks)}")
        summary_lines.append("")

        print(f"Dataset: {spec.name} | files={len(entries)} | parts={len(chunks)}")
        for idx, part_entries in enumerate(chunks, start=1):
            asset_name = f"{dataset_slug}_part{idx:0{digits}d}.zip"
            zip_path = args.temp_dir / asset_name
            planned_size = sum(e.size_bytes for e in part_entries)
            print(f"  [{idx}/{len(chunks)}] {asset_name} planned={planned_size/(1024**3):.2f}GB")

            if args.dry_run:
                continue

            build_zip_part(zip_path, part_entries, compress)
            digest = sha256_file(zip_path)
            sync_release_asset(
                owner,
                repo,
                release_id,
                token,
                zip_path,
                asset_name,
                assets_by_name,
                clobber=args.clobber,
                content_type="application/zip",
            )

            with checksums_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(f"{digest}  {asset_name}\n")

            try:
                zip_path.unlink()
            except OSError:
                pass

            print(f"    uploaded and deleted local part: {asset_name}")

    with notes_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(summary_lines).strip() + "\n")

    if not args.dry_run:
        release_body = "\n".join(summary_lines).strip()
        release = update_release_body(owner, repo, release_id, args.tag, release_body, token)
        sync_release_asset(
            owner,
            repo,
            release_id,
            token,
            notes_path,
            notes_path.name,
            assets_by_name,
            clobber=True,
            content_type="text/markdown; charset=utf-8",
        )
        sync_release_asset(
            owner,
            repo,
            release_id,
            token,
            checksums_path,
            checksums_path.name,
            assets_by_name,
            clobber=True,
            content_type="text/plain; charset=utf-8",
        )

    print(f"Metadata written: {notes_path}")
    print(f"Checksums written: {checksums_path}")
    if not args.dry_run:
        print(f"Release URL: {release.get('html_url', 'n/a')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
