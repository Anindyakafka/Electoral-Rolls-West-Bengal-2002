#!/usr/bin/env python3
"""Independently validate the generated analysis-ready ASD dataset."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import Counter
from pathlib import Path

from build_analysis_dataset import OUTPUT_COLUMNS


DEFAULT_INPUT = Path("data/processed/wb_2025_asd/removed_electors_clean.csv.gz")
DEFAULT_OUTPUT = Path("data/processed/wb_2025_asd/validation.json")
DOMAINS = {
    "gender": {"female", "male", "other"},
    "relation_type": {"father", "husband", "mother", "wife", "other"},
    "uncollectable_reason": {
        "death", "permanently_shifted", "untraceable_or_absent", "already_enrolled"
    },
    "elector_name_status": {"observed", "destroyed_cid0_notdef", "source_blank"},
    "relation_name_status": {"observed", "destroyed_cid0_notdef", "source_blank"},
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    result = {
        "rows": 0, "schema_matches": False, "invalid_record_id": 0,
        "duplicate_document_serial_keys": 0, "documents_reappearing": 0,
        "missing_epic": 0, "invalid_numeric": 0, "name_status_mismatch": 0,
        "invalid_age_flag": 0,
    }
    domain_counts = {name: Counter() for name in DOMAINS}
    current_document = ""
    current_serials: set[int] = set()
    closed_documents: set[str] = set()

    opener = gzip.open if args.input.suffix.lower() == ".gz" else open
    with opener(args.input, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        result["schema_matches"] = reader.fieldnames == OUTPUT_COLUMNS
        for row in reader:
            result["rows"] += 1
            document = row["document_id"]
            if document != current_document:
                if current_document:
                    closed_documents.add(current_document)
                if document in closed_documents:
                    result["documents_reappearing"] += 1
                current_document = document
                current_serials = set()
            try:
                serial = int(row["serial_number"])
                for name in ("source_page", "source_table", "source_row", "district_id", "ac_id",
                             "part_id", "old_part_number", "old_serial_number", "age", "age_above_120"):
                    int(row[name])
            except ValueError:
                result["invalid_numeric"] += 1
                serial = -1
            if serial in current_serials:
                result["duplicate_document_serial_keys"] += 1
            current_serials.add(serial)
            result["invalid_record_id"] += row["record_id"] != f"{document}:{serial}"
            result["missing_epic"] += not row["epic_number"].strip()
            for name, allowed in DOMAINS.items():
                domain_counts[name][row[name]] += 1
            for name in ("elector_name", "relation_name"):
                status = row[f"{name}_status"]
                result["name_status_mismatch"] += (status == "observed") != bool(row[name].strip())
            try:
                result["invalid_age_flag"] += int(row["age_above_120"]) != (int(row["age"]) > 120)
            except ValueError:
                pass
            if result["rows"] % 500_000 == 0:
                print(f"Validated {result['rows']:,} processed rows", flush=True)

    result["domain_counts"] = {name: dict(counts) for name, counts in domain_counts.items()}
    result["invalid_domain_values"] = {
        name: sorted(set(counts) - allowed) for name, (counts, allowed) in
        ((name, (domain_counts[name], DOMAINS[name])) for name in DOMAINS)
    }
    result["checks"] = {
        "expected_rows": result["rows"] == 5_819_543,
        "schema": result["schema_matches"],
        "key": result["invalid_record_id"] == 0
        and result["duplicate_document_serial_keys"] == 0
        and result["documents_reappearing"] == 0,
        "epic_complete": result["missing_epic"] == 0,
        "numeric_fields": result["invalid_numeric"] == 0,
        "name_status_consistent": result["name_status_mismatch"] == 0,
        "age_flag_consistent": result["invalid_age_flag"] == 0,
        "category_domains": not any(result["invalid_domain_values"].values()),
    }
    result["passed"] = all(result["checks"].values())
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
