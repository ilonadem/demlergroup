from __future__ import annotations

import difflib
import email.utils
import html as html_module
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .corpus import detect_document_mismatch, extract_document_text
from .util import normalize_text, sha256_bytes, strip_markup, write_json


DOI_RE = re.compile(r"10\.\d{4,9}/[^\s<>\"'&]+", re.I)
ARXIV_RE = re.compile(
    r"(?:arXiv\s*:?\s*)?((?:\d{4}\.\d{4,5}|[a-z][a-z.-]+/\d{7})(?:v\d+)?)",
    re.I,
)
ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}


class MetadataClient:
    def __init__(self,
                 cache_directory: Path,
                 *,
                 crossref_mailto: str | None = None):
        self.cache_directory = cache_directory
        self.crossref_mailto = crossref_mailto or os.environ.get("CROSSREF_MAILTO", "")
        self._last_crossref_request = 0.0
        self._last_arxiv_request = 0.0

    def crossref_by_doi(self,
                        doi: str) -> dict[str, Any]:
        self._require_crossref_identity()
        encoded_doi = urllib.parse.quote(doi, safe="")
        url = f"https://api.crossref.org/works/{encoded_doi}"
        payload = self._get_json(url,
                                 namespace="crossref",
                                 params={"mailto": self.crossref_mailto},
                                 minimum_interval=0.35)
        return payload["message"]

    def crossref_search(self,
                        citation: str,
                        *,
                        rows: int = 3) -> list[dict[str, Any]]:
        self._require_crossref_identity()
        payload = self._get_json(
            "https://api.crossref.org/works",
            namespace="crossref",
            params={
                "mailto": self.crossref_mailto,
                "query.bibliographic": citation,
                "rows": str(rows),
            },
            minimum_interval=0.35,
        )
        return payload["message"].get("items", [])

    def arxiv_by_id(self,
                    arxiv_id: str) -> dict[str, Any] | None:
        root = self._get_xml(
            "https://export.arxiv.org/api/query",
            namespace="arxiv",
            params={"id_list": arxiv_id},
            minimum_interval=3.0,
        )
        entries = root.findall("atom:entry", ATOM_NAMESPACE)
        return _parse_arxiv_entry(entries[0]) if entries else None

    def arxiv_search(self,
                     title: str) -> list[dict[str, Any]]:
        query = f'ti:"{title}" AND au:Demler'
        root = self._get_xml(
            "https://export.arxiv.org/api/query",
            namespace="arxiv",
            params={"search_query": query, "start": "0", "max_results": "3"},
            minimum_interval=3.0,
        )
        return [
            _parse_arxiv_entry(entry)
            for entry in root.findall("atom:entry", ATOM_NAMESPACE)
        ]

    def _require_crossref_identity(self) -> None:
        if not self.crossref_mailto:
            raise RuntimeError(
                "CROSSREF_MAILTO is required for Crossref enrichment. "
                "Set it to a monitored contact email."
            )

    def _get_json(self,
                  url: str,
                  *,
                  namespace: str,
                  params: dict[str, str],
                  minimum_interval: float) -> dict[str, Any]:
        body = self._get(url,
                         namespace=namespace,
                         params=params,
                         minimum_interval=minimum_interval)
        return json.loads(body.decode("utf-8"))

    def _get_xml(self,
                 url: str,
                 *,
                 namespace: str,
                 params: dict[str, str],
                 minimum_interval: float) -> ET.Element:
        body = self._get(url,
                         namespace=namespace,
                         params=params,
                         minimum_interval=minimum_interval)
        return ET.fromstring(body)

    def _get(self,
             url: str,
             *,
             namespace: str,
             params: dict[str, str],
             minimum_interval: float) -> bytes:
        query = urllib.parse.urlencode(params)
        full_url = f"{url}?{query}" if query else url
        cache_key = sha256_bytes(full_url.encode("utf-8"))
        cache_path = self.cache_directory / namespace / f"{cache_key}.json"
        if cache_path.exists():
            return cache_path.read_bytes()

        previous = (self._last_arxiv_request if namespace == "arxiv"
                    else self._last_crossref_request)
        delay = minimum_interval - (time.monotonic() - previous)
        if delay > 0:
            time.sleep(delay)
        request = urllib.request.Request(
            full_url,
            headers={
                "User-Agent": (
                    "DemlerPublications/0.1 "
                    f"(mailto:{self.crossref_mailto or 'not-used@invalid'})"
                )
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            retry_after = error.headers.get("Retry-After")
            if error.code == 429 and retry_after:
                parsed = email.utils.parsedate_to_datetime(retry_after)
                wait_seconds = float(retry_after) if retry_after.isdigit() else max(
                    0.0, parsed.timestamp() - time.time()
                )
                time.sleep(min(wait_seconds, 60.0))
                with urllib.request.urlopen(request, timeout=30) as response:
                    body = response.read()
            else:
                raise
        if namespace == "arxiv":
            self._last_arxiv_request = time.monotonic()
        else:
            self._last_crossref_request = time.monotonic()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(body)
        return body


def _parse_arxiv_entry(entry: ET.Element) -> dict[str, Any]:
    entry_url = entry.findtext("atom:id", default="", namespaces=ATOM_NAMESPACE)
    identity = entry_url.split("/abs/", 1)[-1]
    versionless_identity = re.sub(r"v\d+$", "", identity)
    published = entry.findtext("atom:published", default="", namespaces=ATOM_NAMESPACE)
    return {
        "arxiv_id": versionless_identity,
        "title": " ".join(
            entry.findtext("atom:title", default="", namespaces=ATOM_NAMESPACE).split()
        ),
        "authors": [
            {"display": author.findtext("atom:name", default="", namespaces=ATOM_NAMESPACE)}
            for author in entry.findall("atom:author", ATOM_NAMESPACE)
        ],
        "published": published[:10],
        "url": f"https://arxiv.org/abs/{versionless_identity}",
    }


def _crossref_title(item: dict[str, Any]) -> str:
    titles = item.get("title") or []
    return strip_markup(titles[0]) if titles else ""


def _crossref_authors(item: dict[str, Any]) -> list[dict[str, str]]:
    authors: list[dict[str, str]] = []
    for author in item.get("author", []):
        given = author.get("given", "").strip()
        family = author.get("family", "").strip()
        display = " ".join(part for part in (given, family) if part)
        if display:
            authors.append({"given": given, "family": family, "display": display})
    return authors


def _crossref_date(item: dict[str, Any]) -> tuple[str, str]:
    candidates: list[tuple[tuple[int, int, int], str, str]] = []
    for key in ("published-online", "published-print", "published", "issued"):
        date_parts = (item.get(key) or {}).get("date-parts") or []
        if not date_parts or not date_parts[0]:
            continue
        values = date_parts[0]
        if len(values) >= 3:
            date = f"{values[0]:04d}-{values[1]:02d}-{values[2]:02d}"
            precision = "day"
        elif len(values) == 2:
            date = f"{values[0]:04d}-{values[1]:02d}"
            precision = "month"
        else:
            date = f"{values[0]:04d}"
            precision = "year"
        comparable = (
            int(values[0]),
            int(values[1]) if len(values) >= 2 else 1,
            int(values[2]) if len(values) >= 3 else 1,
        )
        candidates.append((comparable, date, precision))
    if not candidates:
        return "", ""
    _, date, precision = min(candidates, key=lambda candidate: candidate[0])
    return date, precision


def _contains_demler(authors: list[dict[str, str]]) -> bool:
    return any("demler" in author.get("display", "").casefold() for author in authors)


def _similarity(left: str,
                right: str) -> float:
    normalized_left = normalize_text(left)
    normalized_right = normalize_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    sequence = difflib.SequenceMatcher(None, normalized_left, normalized_right).ratio()
    left_tokens = set(normalized_left.split())
    right_tokens = set(normalized_right.split())
    token_overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
    return 100.0 * max(sequence, token_overlap)


def _candidate_score(record: dict[str, Any],
                     candidate: dict[str, Any]) -> float:
    title = _crossref_title(candidate)
    similarity = max(
        _similarity(record.get("title", ""), title),
        _similarity(record.get("legacy_text", ""), title),
    )
    authors = _crossref_authors(candidate)
    if not _contains_demler(authors):
        return 0.0
    candidate_date, _ = _crossref_date(candidate)
    record_year = record.get("publication_date", "")[:4]
    candidate_year = candidate_date[:4]
    if record_year and candidate_year and abs(int(record_year) - int(candidate_year)) > 1:
        return 0.0
    return similarity


def _apply_crossref(record: dict[str, Any],
                    item: dict[str, Any],
                    *,
                    source: str,
                    score: float) -> None:
    title = _crossref_title(item)
    authors = _crossref_authors(item)
    publication_date, precision = _crossref_date(item)
    doi = (item.get("DOI") or record.get("doi", "")).casefold()
    venues = item.get("short-container-title") or item.get("container-title") or []
    if title:
        record["title"] = title
        record["provenance"]["title"] = source
    if authors:
        record["authors"] = authors
        record["provenance"]["authors"] = source
    if doi:
        record["doi"] = doi
        record["provenance"]["doi"] = source
        record["webpage_url"] = f"https://doi.org/{doi}"
    if venues:
        record["venue"] = strip_markup(venues[0])
        record["provenance"]["venue"] = source
    if item.get("volume"):
        record["volume"] = str(item["volume"])
        record["provenance"]["volume"] = source
    pages = item.get("page") or item.get("article-number") or ""
    if pages:
        record["pages"] = str(pages)
        record["provenance"]["pages"] = source
    if publication_date:
        record["publication_date"] = publication_date
        record["publication_date_precision"] = precision
        if not record.get("first_preprint_date"):
            record["sort_date_source"] = "publication"
    record["confidence"] = round(score / 100.0, 4)
    record["issues"] = [issue for issue in record["issues"] if issue != "metadata_unresolved"]
    record["review_status"] = "accepted" if not _blocking_issues(record) else "needs_review"


def _apply_arxiv(record: dict[str, Any],
                 item: dict[str, Any],
                 *,
                 source: str) -> None:
    record["arxiv_id"] = item["arxiv_id"]
    record["first_preprint_date"] = item["published"]
    record["sort_date_source"] = "arxiv"
    record["provenance"]["arxiv_id"] = source
    record["provenance"]["first_preprint_date"] = source
    if not record.get("doi"):
        record["webpage_url"] = item["url"]
    if not record.get("title") and item.get("title"):
        record["title"] = item["title"]
        record["authors"] = item["authors"]
        record["provenance"]["title"] = source
        record["provenance"]["authors"] = source
    record["issues"] = [issue for issue in record["issues"] if issue != "metadata_unresolved"]
    record["review_status"] = "accepted" if not _blocking_issues(record) else "needs_review"


def _blocking_issues(record: dict[str, Any]) -> list[str]:
    non_blocking = {
        "discarded_document_arxiv",
        "missing_file",
        "missing_webpage",
        "wrong_file",
    }
    return [
        issue for issue in record.get("issues", [])
        if issue not in non_blocking and not issue.startswith("metadata_error:")
    ]


def discover_identifiers(record: dict[str, Any],
                         document_text: str) -> None:
    doi_candidates = [
        match.group(0).rstrip(".,;:)]}").casefold()
        for match in DOI_RE.finditer(document_text)
    ]
    arxiv_candidates = [
        re.sub(r"v\d+$", "", match.group(1), flags=re.I)
        for match in ARXIV_RE.finditer(document_text)
    ]
    if not record.get("doi") and doi_candidates:
        record["doi"] = doi_candidates[0]
        record["provenance"]["doi"] = "document_text"
    if not record.get("arxiv_id") and arxiv_candidates:
        record["arxiv_id"] = arxiv_candidates[0]
        record["provenance"]["arxiv_id"] = "document_text"


def enrich_database(database: dict[str, Any],
                    *,
                    corpus_folder: Path,
                    client: MetadataClient,
                    search_arxiv: bool = False,
                    maximum_records: int | None = None) -> dict[str, Any]:
    processed = 0
    for record in database["records"]:
        if maximum_records is not None and processed >= maximum_records:
            break
        record["issues"] = [
            issue for issue in record.get("issues", [])
            if issue not in {
                "metadata_unresolved",
                "doi_metadata_mismatch",
                "arxiv_metadata_mismatch",
                "wrong_file",
            } and not issue.startswith("metadata_error:")
        ]
        filename = record.get("file", {}).get("filename", "")
        document_text = ""
        if filename:
            document_text = extract_document_text(corpus_folder / filename)
            discover_identifiers(record, document_text)

        try:
            if record.get("doi"):
                candidate = client.crossref_by_doi(record["doi"])
                score = _candidate_score(record, candidate)
                if score >= 85.0:
                    _apply_crossref(record, candidate, source="crossref_doi", score=score)
                elif "doi_metadata_mismatch" not in record["issues"]:
                    record["issues"].append("doi_metadata_mismatch")
            else:
                candidates = client.crossref_search(record["legacy_text"])
                scored = sorted(
                    ((_candidate_score(record, candidate), candidate) for candidate in candidates),
                    key=lambda item: item[0],
                    reverse=True,
                )
                leading_score = scored[0][0] if scored else 0.0
                runner_up = scored[1][0] if len(scored) > 1 else 0.0
                if leading_score >= 95.0 and leading_score - runner_up >= 5.0:
                    _apply_crossref(
                        record,
                        scored[0][1],
                        source="crossref_search",
                        score=leading_score,
                    )
                elif (not record.get("arxiv_id")
                      and "override" not in record.get("provenance", {})
                      and "metadata_unresolved" not in record["issues"]):
                    record["issues"].append("metadata_unresolved")

            if record.get("arxiv_id"):
                arxiv_item = client.arxiv_by_id(record["arxiv_id"])
                if arxiv_item:
                    arxiv_score = _similarity(record.get("title", ""),
                                              arxiv_item["title"])
                    identifier_source = record.get("provenance", {}).get("arxiv_id")
                    if identifier_source != "document_text" or arxiv_score >= 95.0:
                        _apply_arxiv(record, arxiv_item, source="arxiv_id")
                    else:
                        record["arxiv_id"] = ""
                        record["provenance"]["arxiv_id"] = ""
                        record["provenance"]["first_preprint_date"] = ""
                        record["first_preprint_date"] = ""
                        record["issues"].append("discarded_document_arxiv")
                        if search_arxiv and record.get("title"):
                            candidates = client.arxiv_search(record["title"])
                            scored = sorted(
                                ((_similarity(record["title"], candidate["title"]), candidate)
                                 for candidate in candidates),
                                key=lambda item: item[0],
                                reverse=True,
                            )
                            if scored and scored[0][0] >= 95.0:
                                _apply_arxiv(record,
                                             scored[0][1],
                                             source="arxiv_search")
            elif search_arxiv and record.get("title"):
                candidates = client.arxiv_search(record["title"])
                scored = sorted(
                    ((_similarity(record["title"], candidate["title"]), candidate)
                     for candidate in candidates),
                    key=lambda item: item[0],
                    reverse=True,
                )
                if scored and scored[0][0] >= 95.0:
                    _apply_arxiv(record, scored[0][1], source="arxiv_search")
        except (urllib.error.URLError, KeyError, ValueError, RuntimeError) as error:
            issue = f"metadata_error:{type(error).__name__}"
            if issue not in record["issues"]:
                record["issues"].append(issue)

        if document_text and detect_document_mismatch(record, document_text):
            if "wrong_file" not in record["issues"]:
                record["issues"].append("wrong_file")
        record["review_status"] = "accepted" if not _blocking_issues(record) else "needs_review"
        processed += 1
    return database


def write_review_reports(database: dict[str, Any],
                         *,
                         json_path: Path,
                         html_path: Path) -> int:
    records = [
        {
            "ref_id": record["ref_id"],
            "title": record.get("title", ""),
            "legacy_text": record.get("legacy_text", ""),
            "issues": record.get("issues", []),
            "file": record.get("file", {}).get("filename", ""),
        }
        for record in database["records"]
        if record.get("review_status") != "accepted" or record.get("issues")
    ]
    write_json(json_path, {"records": records})
    rows = "\n".join(
        "<tr>"
        f"<td>{html_module.escape(record['ref_id'])}</td>"
        f"<td>{html_module.escape(strip_markup(record['title']))}</td>"
        f"<td>{html_module.escape(', '.join(record['issues']))}</td>"
        f"<td>{html_module.escape(record['file'])}</td>"
        "</tr>"
        for record in records
    )
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>Publication migration review</title>"
        "<style>body{font-family:system-ui;margin:2rem}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #ccd5e0;padding:.5rem;text-align:left;vertical-align:top}</style>"
        "</head><body><h1>Publication migration review</h1>"
        f"<p>{len(records)} records have review notes.</p>"
        "<table><thead><tr><th>Ref</th><th>Title</th><th>Issues</th><th>File</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></body></html>\n",
        encoding="utf-8",
    )
    return len(records)
