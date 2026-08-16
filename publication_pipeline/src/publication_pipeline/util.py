from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any, Iterable


INLINE_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[^\w]+", re.UNICODE)


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "windows-1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def write_json(path: Path,
               payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload,
                          ensure_ascii=False,
                          indent=2,
                          sort_keys=False)
    path.write_text(rendered + "\n", encoding="utf-8")


def read_json(path: Path,
              *,
              default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dropbox_content_hash(path: Path) -> str:
    block_hashes = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(4 * 1024 * 1024)
            if not block:
                break
            block_hashes.update(hashlib.sha256(block).digest())
    return block_hashes.hexdigest()


def strip_markup(fragment: str,
                 *,
                 preserve_breaks: bool = False) -> str:
    if preserve_breaks:
        fragment = re.sub(r"<\s*br\s*/?\s*>", "\n", fragment, flags=re.I)
        fragment = re.sub(r"<\s*/\s*div\s*>", "\n", fragment, flags=re.I)
    text = INLINE_TAG_RE.sub(" ", fragment)
    text = html.unescape(text).replace("\xa0", " ")
    if preserve_breaks:
        lines = [WHITESPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_text(value: str) -> str:
    value = html.unescape(INLINE_TAG_RE.sub(" ", value)).casefold()
    value = value.replace("\\(", " ").replace("\\)", " ")
    return WHITESPACE_RE.sub(" ", WORD_RE.sub(" ", value)).strip()


def unique_preserving_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
