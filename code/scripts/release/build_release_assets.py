#!/usr/bin/env python3
"""Build GitHub Release-friendly zip assets from large data directories.

This script is designed for very large dataset folders that cannot be committed to git.
It splits files into multiple zip parts based on a maximum part size, writes SHA256
checksums, and generates helper commands for GitHub Release upload via gh CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple
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
        entries.append(
            FileEntry(
                source=path,
                relative=relative,
                size_bytes=path.stat().st_size,
            )
        )
    return entries


def chunk_files(entries: Sequence[FileEntry], max_part_bytes: int) -> List[List[FileEntry]]:
    if max_part_bytes <= 0:
        raise ValueError("max_part_bytes must be positive.")

    chunks: List[List[FileEntry]] = []
    current_chunk: List[FileEntry] = []
    current_size = 0

    for entry in entries:
        file_size = entry.size_bytes

        if current_chunk and current_size + file_size > max_part_bytes:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0

        current_chunk.append(entry)
        current_size += file_size

        if file_size > max_part_bytes:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def compression_mode(name: str) -> int:
    return ZIP_DEFLATED if name == "deflated" else ZIP_STORED


def remove_existing_parts(dataset_dir: Path, dataset_slug: str) -> None:
    pattern = f"{dataset_slug}_part*.zip"
    for existing in dataset_dir.glob(pattern):
        if existing.is_file():
            existing.unlink()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_zip_part(
    output_zip: Path,
    part_entries: Sequence[FileEntry],
    compress: int,
) -> None:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_zip, mode="w", compression=compress, allowZip64=True) as archive:
        for entry in part_entries:
            archive.write(entry.source, arcname=entry.relative.as_posix())


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{size} B"


def build_release_commands(
    tag: str,
    asset_paths: Sequence[Path],
    notes_path: Path,
) -> str:
    lines = [
        f"gh release create {tag} --title \"{tag}\" --notes-file \"{notes_path}\"",
        f"gh release upload {tag} \"{notes_path.parent / 'sha256sums.txt'}\"",
    ]
    for asset in asset_paths:
        lines.append(f"gh release upload {tag} \"{asset}\"")
    return "\n".join(lines)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build release zip parts from large data folders.")
    parser.add_argument(
        "--source",
        action="append",
        type=parse_source,
        required=True,
        help="Dataset source in NAME=PATH format; repeat for multiple datasets.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data") / "release_assets",
        help="Directory where release assets will be written.",
    )
    parser.add_argument(
        "--max-part-size-gb",
        type=float,
        default=1.8,
        help="Maximum target size per zip part in GB.",
    )
    parser.add_argument(
        "--compression",
        choices=["stored", "deflated"],
        default="stored",
        help="Zip compression mode. 'stored' is fastest and safest for large PDFs.",
    )
    parser.add_argument(
        "--tag",
        default="wb-electoral-rolls-data",
        help="GitHub release tag to use in generated commands.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan parts without writing zip files.",
    )
    parser.add_argument(
        "--preserve-root-folder",
        dest="preserve_root_folder",
        action="store_true",
        help="Store files under their source root folder names inside zip parts.",
    )
    parser.add_argument(
        "--no-preserve-root-folder",
        dest="preserve_root_folder",
        action="store_false",
        help="Store files directly relative to source root (without top folder).",
    )
    parser.set_defaults(preserve_root_folder=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)

    max_part_bytes = int(args.max_part_size_gb * (1024 ** 3))
    if max_part_bytes <= 0:
        print("max part size must be greater than zero", file=sys.stderr)
        return 2

    output_root = args.output_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    all_assets: List[Path] = []
    summary_lines: List[str] = ["# Electoral Rolls Data Release", ""]

    for spec in args.source:
        source_dir = spec.path
        if not source_dir.exists() or not source_dir.is_dir():
            print(f"Source directory not found: {source_dir}", file=sys.stderr)
            return 1

        dataset_slug = slugify(spec.name)
        dataset_dir = output_root / dataset_slug
        entries = collect_files(source_dir, args.preserve_root_folder)
        chunks = chunk_files(entries, max_part_bytes)

        if not args.dry_run:
            dataset_dir.mkdir(parents=True, exist_ok=True)
            remove_existing_parts(dataset_dir, dataset_slug)

        source_total_size = sum(entry.size_bytes for entry in entries)
        summary_lines.append(f"## {spec.name}")
        summary_lines.append(f"- Source: {source_dir}")
        summary_lines.append(f"- Files: {len(entries)}")
        summary_lines.append(f"- Total size: {format_bytes(source_total_size)}")
        summary_lines.append(f"- Planned parts: {len(chunks)}")
        summary_lines.append("")

        print(f"Dataset: {spec.name}")
        print(f"  Source: {source_dir}")
        print(f"  Files: {len(entries)}")
        print(f"  Size : {format_bytes(source_total_size)}")
        print(f"  Parts: {len(chunks)}")

        digits = max(3, int(math.log10(max(1, len(chunks)))) + 1)
        compress = compression_mode(args.compression)

        for idx, part_entries in enumerate(chunks, start=1):
            part_name = f"{dataset_slug}_part{idx:0{digits}d}.zip"
            part_path = dataset_dir / part_name
            part_size = sum(entry.size_bytes for entry in part_entries)
            print(f"    - {part_name} (planned: {format_bytes(part_size)}, files: {len(part_entries)})")

            if not args.dry_run:
                write_zip_part(part_path, part_entries, compress)
            all_assets.append(part_path)

    checksums_path = output_root / "sha256sums.txt"
    notes_path = output_root / "release_notes.md"
    commands_path = output_root / "gh_release_commands.txt"

    if not args.dry_run:
        with checksums_path.open("w", encoding="utf-8", newline="\n") as handle:
            for asset in all_assets:
                digest = sha256_file(asset)
                handle.write(f"{digest}  {asset.name}\n")

        with notes_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(summary_lines).strip() + "\n")

        commands = build_release_commands(args.tag, all_assets, notes_path)
        with commands_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(commands + "\n")

        print("\nArtifacts written:")
        print(f"  - {notes_path}")
        print(f"  - {checksums_path}")
        print(f"  - {commands_path}")
    else:
        print("\nDry run only. No zip files or checksums were written.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
