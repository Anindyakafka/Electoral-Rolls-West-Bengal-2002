#!/usr/bin/env python3
"""Build the row-preserving, analysis-ready WB 2025 ASD dataset.

The transformation is streaming and keeps the raw CSV immutable.  It standardizes
multilingual categories, converts numeric fields, normalizes stable identifiers,
and attaches source-damage statuses from the missing-name classification sidecar.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import unicodedata
from collections import Counter
from pathlib import Path


DEFAULT_INPUT = Path("data/interim/wb_2025_asd/removed_electors_raw.csv")
DEFAULT_CLASSIFICATION = Path("data/interim/wb_2025_asd/missing_name_source_classification.csv")
DEFAULT_OUTPUT = Path("data/processed/wb_2025_asd/removed_electors_clean.csv.gz")
DEFAULT_QA = Path("data/processed/wb_2025_asd/cleaning_qa.json")

GENDER_MAP = {
    "মহিলা": "female", "F": "female", "महिला": "female",
    "পুরুষ": "male", "M": "male", "पुरुष": "male",
    "অন্যান্য": "other", "O": "other",
}
RELATION_MAP = {
    "বাবা": "father", "Father": "father", "पिता": "father",
    "স্বামী": "husband", "Husband": "husband", "पति": "husband",
    "মা": "mother", "Mother": "mother", "माँ": "mother",
    "স্ত্রী": "wife", "Wife": "wife", "पत्नी": "wife",
    "অন্যান্য": "other", "Other": "other", "अन्य": "other",
}
REASON_MAP = {
    "মৃত": "death", "Death": "death", "मृत्यु": "death",
    "স্থায়ীভাবে স্থানান্তরিত": "permanently_shifted",
    "Permanently Shifted": "permanently_shifted",
    "स्थायी रूप से स्थानांतरित": "permanently_shifted",
    "খুঁজে পাওয়া যায়নি / অনুপস্থিত": "untraceable_or_absent",
    "Untraceable/Absent": "untraceable_or_absent",
    "पता न लगने योग्य/अनुपस्थित": "untraceable_or_absent",
    "ইতিমধ্যে তালিকাভুক্ত": "already_enrolled",
    "Already enrolled": "already_enrolled",
    "पहले से नामांकित": "already_enrolled",
}
DISTRICT_NAMES = {
    1: "Cooch Behar", 2: "Jalpaiguri", 3: "Darjeeling", 4: "Uttar Dinajpur",
    5: "Dakshin Dinajpur", 6: "Malda", 7: "Murshidabad", 8: "Nadia",
    9: "North 24 Parganas", 10: "South 24 Parganas", 11: "Kolkata North",
    12: "Kolkata South", 14: "Howrah", 15: "Hooghly", 16: "Purba Medinipur",
    17: "Paschim Medinipur", 18: "Purulia", 19: "Bankura", 20: "Purba Bardhaman",
    21: "Birbhum", 22: "Alipurduar", 23: "Kalimpong", 24: "Jhargram",
    25: "Paschim Bardhaman",
}
OUTPUT_COLUMNS = [
    "record_id", "document_id", "source_relative_path", "source_page", "source_table",
    "source_row", "district_id", "district_name", "district_slug", "ac_id", "ac_name",
    "ac_slug", "part_id", "serial_number", "epic_number", "elector_name",
    "elector_name_status", "relation_type", "relation_type_raw", "relation_name",
    "relation_name_status", "old_part_number", "old_serial_number", "age",
    "age_above_120", "gender", "gender_raw", "uncollectable_reason",
    "uncollectable_reason_raw",
]


def clean_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value or "").replace("\u00a0", " ").split())


def title_slug(value: str) -> str:
    return " ".join(word.capitalize() for word in value.replace("-", " ").split())


def classification_key(row: dict[str, str], field: str) -> tuple[str, ...]:
    return (row["document_id"], row["source_page"], row["source_table"], row["source_row"], field)


def load_name_statuses(path: Path) -> dict[tuple[str, ...], str]:
    statuses: dict[tuple[str, ...], str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = tuple(row[name] for name in
                        ("document_id", "source_page", "source_table", "source_row", "missing_field"))
            if key in statuses:
                raise ValueError(f"Duplicate missing-name classification key: {key}")
            statuses[key] = row["source_condition"]
    return statuses


def open_output(path: Path, compressed: bool):
    if compressed:
        return gzip.open(path, "wt", encoding="utf-8", newline="", compresslevel=3)
    return path.open("w", encoding="utf-8-sig", newline="")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--classification", type=Path, default=DEFAULT_CLASSIFICATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--qa", type=Path, default=DEFAULT_QA)
    args = parser.parse_args()

    for path in (args.input, args.classification):
        if not path.is_file():
            raise SystemExit(f"Required input not found: {path}")
    statuses = load_name_statuses(args.classification)
    used_statuses: set[tuple[str, ...]] = set()
    counts: dict[str, Counter[str]] = {
        "gender": Counter(), "relation_type": Counter(), "reason": Counter(),
        "elector_name_status": Counter(), "relation_name_status": Counter(),
    }
    rows = 0
    duplicate_record_ids = 0
    previous_record_id = ""
    unmapped: dict[str, Counter[str]] = {
        "gender": Counter(), "relation_type": Counter(), "reason": Counter(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.qa.parent.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_name(args.output.name + ".partial")

    try:
        with args.input.open("r", encoding="utf-8-sig", newline="") as source, open_output(
            partial, args.output.suffix.lower() == ".gz"
        ) as target:
            reader = csv.DictReader(source)
            writer = csv.DictWriter(target, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            for raw in reader:
                district_id = int(raw["district_id"])
                serial = int(raw["serial_number_raw"])
                record_id = f'{raw["document_id"]}:{serial}'
                duplicate_record_ids += record_id == previous_record_id
                previous_record_id = record_id

                elector_name = clean_text(raw["elector_name_raw"])
                relation_name = clean_text(raw["relation_name_raw"])
                name_status = {}
                for field, value in (("elector_name_raw", elector_name), ("relation_name_raw", relation_name)):
                    output_name = field.removesuffix("_raw") + "_status"
                    if value:
                        name_status[output_name] = "observed"
                    else:
                        key = classification_key(raw, field)
                        if key not in statuses:
                            raise ValueError(f"Missing source classification for {key}")
                        name_status[output_name] = statuses[key]
                        used_statuses.add(key)

                gender_raw = clean_text(raw["gender_raw"])
                relation_raw = clean_text(raw["relation_type_raw"])
                reason_raw = clean_text(raw["uncollectable_reason_raw"])
                gender = GENDER_MAP.get(gender_raw, "unmapped")
                relation = RELATION_MAP.get(relation_raw, "unmapped")
                reason = REASON_MAP.get(reason_raw, "unmapped")
                for name, raw_value, clean_value in (
                    ("gender", gender_raw, gender), ("relation_type", relation_raw, relation),
                    ("reason", reason_raw, reason),
                ):
                    counts[name][clean_value] += 1
                    if clean_value == "unmapped":
                        unmapped[name][raw_value] += 1
                counts["elector_name_status"][name_status["elector_name_status"]] += 1
                counts["relation_name_status"][name_status["relation_name_status"]] += 1

                age = int(raw["age_raw"])
                writer.writerow({
                    "record_id": record_id, "document_id": raw["document_id"],
                    "source_relative_path": raw["source_relative_path"],
                    "source_page": int(raw["source_page"]), "source_table": int(raw["source_table"]),
                    "source_row": int(raw["source_row"]), "district_id": district_id,
                    "district_name": DISTRICT_NAMES[district_id], "district_slug": raw["district_slug"],
                    "ac_id": int(raw["ac_id"]), "ac_name": title_slug(raw["ac_slug"]),
                    "ac_slug": raw["ac_slug"], "part_id": int(raw["part_id"]),
                    "serial_number": serial, "epic_number": clean_text(raw["epic_number_raw"]).upper(),
                    "elector_name": elector_name, **name_status, "relation_type": relation,
                    "relation_type_raw": relation_raw, "relation_name": relation_name,
                    "old_part_number": int(raw["old_part_number_raw"]),
                    "old_serial_number": int(raw["old_serial_number_raw"]), "age": age,
                    "age_above_120": int(age > 120), "gender": gender, "gender_raw": gender_raw,
                    "uncollectable_reason": reason, "uncollectable_reason_raw": reason_raw,
                })
                rows += 1
                if rows % 500_000 == 0:
                    print(f"Cleaned {rows:,} rows", flush=True)
        os.replace(partial, args.output)
    except BaseException:
        if partial.exists():
            partial.unlink()
        raise

    qa = {
        "input": str(args.input), "output": str(args.output), "rows": rows,
        "output_bytes": args.output.stat().st_size, "duplicate_adjacent_record_ids": duplicate_record_ids,
        "missing_name_classifications_available": len(statuses),
        "missing_name_classifications_used": len(used_statuses),
        "unused_missing_name_classifications": len(statuses) - len(used_statuses),
        "counts": {name: dict(counter) for name, counter in counts.items()},
        "unmapped_raw_values": {name: dict(counter) for name, counter in unmapped.items()},
        "checks": {
            "row_count_matches_validated_raw": rows == 5_819_543,
            "record_ids_unique_in_source_order": duplicate_record_ids == 0,
            "all_missing_name_cells_classified": len(used_statuses) == len(statuses),
            "all_categories_mapped": not any(unmapped.values()),
        },
    }
    qa["passed"] = all(qa["checks"].values())
    args.qa.write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(qa, ensure_ascii=False, indent=2))
    return 0 if qa["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
