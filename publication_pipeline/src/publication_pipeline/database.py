from __future__ import annotations

import copy
import difflib
from collections import defaultdict
from pathlib import Path
from typing import Any

from .util import normalize_text, read_json, write_json


def apply_overrides(database: dict[str, Any],
                    overrides_path: Path) -> dict[str, Any]:
    overrides = read_json(overrides_path, default={}) or {}
    record_overrides = overrides.get("records", {})
    updated = copy.deepcopy(database)
    by_ref = {record["ref_id"]: record for record in updated["records"]}
    for ref_id, fields in record_overrides.items():
        if ref_id not in by_ref:
            raise ValueError(f"Override references unknown publication: {ref_id}")
        _deep_update(by_ref[ref_id], fields)
        by_ref[ref_id].setdefault("provenance", {})["override"] = "data/overrides.json"
    return updated


def _deep_update(target: dict[str, Any],
                 changes: dict[str, Any]) -> None:
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def detect_identity_collisions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    collisions: list[dict[str, Any]] = []
    active_records = [record for record in records if not record.get("duplicate_of")]
    for field in ("doi", "arxiv_id"):
        by_value: dict[str, list[str]] = defaultdict(list)
        for record in active_records:
            value = record.get(field, "").casefold()
            if field == "arxiv_id":
                value = value.split("v", 1)[0]
            if value:
                by_value[value].append(record["ref_id"])
        collisions.extend(
            {"kind": f"duplicate_{field}", "value": value, "ref_ids": ref_ids}
            for value, ref_ids in sorted(by_value.items())
            if len(ref_ids) > 1
        )
    titled_records = [
        (record["ref_id"], normalize_text(record.get("title", "")))
        for record in active_records
        if len(normalize_text(record.get("title", ""))) >= 24
    ]
    for left_index, (left_ref, left_title) in enumerate(titled_records):
        left_tokens = set(left_title.split())
        for right_ref, right_title in titled_records[left_index + 1:]:
            length_ratio = min(len(left_title), len(right_title)) / max(
                len(left_title), len(right_title)
            )
            if length_ratio < 0.9:
                continue
            right_tokens = set(right_title.split())
            token_overlap = len(left_tokens & right_tokens) / max(
                1, min(len(left_tokens), len(right_tokens))
            )
            sequence_ratio = difflib.SequenceMatcher(None, left_title, right_title).ratio()
            if token_overlap >= 0.95 and sequence_ratio >= 0.97:
                collisions.append({
                    "kind": "near_duplicate_title",
                    "value": left_title,
                    "ref_ids": [left_ref, right_ref],
                })
    return collisions


def save_database(path: Path,
                  database: dict[str, Any]) -> None:
    write_json(path, database)
