from __future__ import annotations

import html.parser
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .database import detect_identity_collisions
from .render import sorted_active_records
from .util import write_json


class GeneratedListParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ref_ids: list[str] = []
        self.years: list[str] = []
        self.title_count = 0
        self.author_count = 0
        self.citation_count = 0
        self.doi_count = 0
        self.control_count = 0

    def handle_starttag(self,
                        tag: str,
                        attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "article" and "experimental-publication" in classes:
            self.ref_ids.append(attributes.get("data-ref") or "")
        if tag == "section" and "publication-year" in classes:
            self.years.append(attributes.get("data-year") or "")
        self.title_count += "experimental-publication-title" in classes
        self.author_count += "experimental-publication-authors" in classes
        self.citation_count += "experimental-publication-citation" in classes
        self.doi_count += "experimental-publication-doi" in classes
        self.control_count += "publication-control" in classes


def validate_database(database: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    records = database.get("records", [])
    ref_ids = [record.get("ref_id", "") for record in records]
    if len(records) != 455:
        errors.append(f"Expected 455 records, found {len(records)}")
    if len(set(ref_ids)) != len(ref_ids):
        errors.append("Duplicate refNNN identifiers in database")
    expected = {f"ref{number}" for number in range(1, 456)}
    if set(ref_ids) != expected:
        errors.append("Database refNNN set is not exactly ref1 through ref455")
    legacy_orders = [record.get("legacy_order") for record in records]
    if sorted(legacy_orders) != list(range(1, 456)):
        errors.append("Database legacy order is not exactly 1 through 455")
    for collision in detect_identity_collisions(records):
        errors.append(
            f"{collision['kind']} {collision['value']} in {', '.join(collision['ref_ids'])}"
        )
    return errors


def validate_generated_list(database: dict[str, Any],
                            path: Path) -> list[str]:
    errors: list[str] = []
    parser = GeneratedListParser()
    parser.feed(path.read_text(encoding="utf-8"))
    active = sorted_active_records(database["records"])
    expected_ref_ids = [record["ref_id"] for record in active]
    expected_count = len(active)
    if len(parser.ref_ids) != expected_count:
        errors.append(
            f"Expected {expected_count} rendered publications, found {len(parser.ref_ids)}"
        )
    if len(set(parser.ref_ids)) != len(parser.ref_ids):
        errors.append("Generated publication IDs are not unique")
    if parser.ref_ids != expected_ref_ids:
        errors.append("Generated publications do not preserve legacy display order")
    for label, count in (
        ("titles", parser.title_count),
        ("authors", parser.author_count),
        ("citations", parser.citation_count),
        ("DOI lines", parser.doi_count),
    ):
        if count != expected_count:
            errors.append(f"Expected {expected_count} {label}, found {count}")
    if parser.control_count != expected_count * 2:
        errors.append(
            f"Expected {expected_count * 2} controls, found {parser.control_count}"
        )
    return errors


def check_live_links(records: list[dict[str, Any]],
                     *,
                     output_path: Path) -> list[str]:
    urls: dict[str, list[str]] = {}
    for record in records:
        for url in (
            record.get("file", {}).get("dropbox_url", ""),
            record.get("webpage_url", ""),
        ):
            if url:
                urls.setdefault(url, []).append(record["ref_id"])
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, (url, ref_ids) in enumerate(sorted(urls.items()), start=1):
        status, state = _probe_link(url)
        results.append({"url": url, "ref_ids": ref_ids, "status": status, "state": state})
        if state == "failed" or state.startswith("network_error"):
            errors.append(
                f"Link check failed for {', '.join(ref_ids)}: {url} "
                f"({f'HTTP {status}' if status else state})"
            )
        if index < len(urls):
            time.sleep(0.1)
    write_json(output_path, {"results": results})
    return errors


def _probe_link(url: str) -> tuple[int, str]:
    last_network_error = ""
    for attempt in range(2):
        for method in ("HEAD", "GET"):
            headers = {"User-Agent": "DemlerPublicationsLinkCheck/0.1"}
            if method == "GET":
                headers["Range"] = "bytes=0-0"
            request = urllib.request.Request(url, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    status = response.status
                return status, "ok" if 200 <= status < 400 else "failed"
            except urllib.error.HTTPError as error:
                status = error.code
                if status in {401, 403, 429}:
                    return status, "blocked"
                if method == "HEAD" and status in {404, 405, 500, 501}:
                    continue
                if status >= 500 and attempt == 0:
                    break
                return status, "failed"
            except urllib.error.URLError as error:
                last_network_error = str(error.reason)
                if attempt == 0:
                    break
        if attempt == 0:
            time.sleep(0.5)
    return 0, f"network_error:{last_network_error or 'unknown'}"


def write_check_report(path: Path,
                       *,
                       errors: list[str]) -> None:
    write_json(path, {"ok": not errors, "errors": errors})
