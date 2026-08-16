from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from .util import dropbox_content_hash, normalize_text, sha256_file


FILE_RE = re.compile(
    r"^ref(?P<number>\d+)(?P<suffix>[a-z_][a-z0-9_]*)?\.(?P<extension>pdf|ps)$",
    re.I,
)
PRIMARY_ALIAS = {
    "ref71": "ref71a.pdf",
    "ref74": "ref74a.pdf",
}
def _candidate_priority(ref_id: str,
                        path: Path) -> tuple[int, str]:
    exact_pdf = f"{ref_id}.pdf".casefold()
    exact_ps = f"{ref_id}.ps".casefold()
    filename = path.name.casefold()
    if filename == exact_pdf:
        return 0, filename
    if filename == PRIMARY_ALIAS.get(ref_id, "").casefold():
        return 1, filename
    if filename == exact_ps:
        return 2, filename
    return 10, filename


def scan_local_corpus(folder: Path,
                      *,
                      hash_files: bool = False) -> dict[str, Any]:
    if not folder.is_dir():
        raise FileNotFoundError(f"Dropbox publication folder not found: {folder}")

    candidates_by_ref: dict[str, list[Path]] = defaultdict(list)
    unrecognized: list[str] = []
    for path in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file():
            continue
        match = FILE_RE.match(path.name)
        if not match:
            unrecognized.append(path.name)
            continue
        ref_id = f"ref{int(match.group('number'))}"
        candidates_by_ref[ref_id].append(path)

    selected: dict[str, dict[str, Any]] = {}
    ignored_variants: list[dict[str, str]] = []
    for ref_id, paths in sorted(candidates_by_ref.items(), key=lambda item: int(item[0][3:])):
        ranked = sorted(paths, key=lambda path: _candidate_priority(ref_id, path))
        primary = ranked[0] if _candidate_priority(ref_id, ranked[0])[0] < 10 else None
        if primary is not None:
            file_data = {
                "filename": primary.name,
                "kind": primary.suffix.lstrip(".").upper(),
                "size": primary.stat().st_size,
                "sha256": "",
                "dropbox_content_hash": "",
                "dropbox_url": "",
                "link_status": "unlinked",
            }
            if hash_files:
                file_data["sha256"] = sha256_file(primary)
                file_data["dropbox_content_hash"] = dropbox_content_hash(primary)
            selected[ref_id] = file_data
        for variant in paths:
            if variant != primary:
                ignored_variants.append({"ref_id": ref_id, "filename": variant.name})

    if not hash_files:
        by_size: dict[int, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        for ref_id, file_data in selected.items():
            by_size[file_data["size"]].append((ref_id, file_data))
        for same_size_files in by_size.values():
            if len(same_size_files) < 2:
                continue
            for _, file_data in same_size_files:
                path = folder / file_data["filename"]
                file_data["sha256"] = sha256_file(path)
                file_data["dropbox_content_hash"] = dropbox_content_hash(path)

    return {
        "selected": selected,
        "ignored_variants": ignored_variants,
        "unrecognized": unrecognized,
    }


def merge_corpus(records: list[dict[str, Any]],
                 inventory: dict[str, Any]) -> None:
    selected = inventory["selected"]
    for record in records:
        file_data = selected.get(record["ref_id"])
        if file_data:
            existing_url = record.get("file", {}).get("dropbox_url", "")
            record["file"] = dict(file_data)
            if existing_url:
                record["file"]["dropbox_url"] = existing_url
                record["file"]["link_status"] = "linked"
        else:
            record["file"] = {
                "filename": "",
                "kind": "",
                "size": 0,
                "sha256": "",
                "dropbox_content_hash": "",
                "dropbox_url": "",
                "link_status": "missing",
            }
            if "missing_file" not in record["issues"]:
                record["issues"].append("missing_file")


def extract_document_text(path: Path,
                          *,
                          max_characters: int = 80_000) -> str:
    if path.suffix.casefold() == ".pdf":
        command = ["pdftotext", "-f", "1", "-l", "2", "-layout", str(path), "-"]
    elif path.suffix.casefold() == ".ps":
        command = ["ps2ascii", str(path)]
    else:
        return ""
    result = subprocess.run(command,
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=60)
    if result.returncode != 0:
        return ""
    return result.stdout[:max_characters]


def find_content_collisions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_hash: dict[str, list[str]] = defaultdict(list)
    for record in records:
        digest = record.get("file", {}).get("sha256", "")
        if digest:
            by_hash[digest].append(record["ref_id"])
    return [
        {"sha256": digest, "ref_ids": ref_ids}
        for digest, ref_ids in sorted(by_hash.items())
        if len(ref_ids) > 1
    ]


def detect_document_mismatch(record: dict[str, Any],
                             document_text: str) -> bool:
    if not record.get("title") or not document_text:
        return False
    document_excerpt = document_text[:12_000]
    normalized_document = normalize_text(document_excerpt)
    normalized_title = normalize_text(record["title"])
    if normalized_title and normalized_title in normalized_document:
        return False

    doi = record.get("doi", "").casefold()
    if doi and doi in document_excerpt.casefold():
        return False

    arxiv_id = re.sub(r"v\d+$", "", record.get("arxiv_id", ""), flags=re.I)
    if arxiv_id and arxiv_id.casefold() in document_excerpt.casefold():
        return False

    prominent_arxiv_ids = {
        re.sub(r"v\d+$", "", candidate, flags=re.I).casefold()
        for candidate in re.findall(
            r"arXiv\s*:?\s*((?:\d{4}\.\d{4,5}|[a-z][a-z.-]+/\d{7})(?:v\d+)?)",
            document_excerpt[:4_000],
            flags=re.I,
        )
    }
    return bool(arxiv_id and prominent_arxiv_ids
                and arxiv_id.casefold() not in prominent_arxiv_ids)
