from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any


BLOCKING_ISSUES = {
    "metadata_unresolved",
    "multiple_doi_candidates",
    "multiple_arxiv_candidates",
    "doi_metadata_mismatch",
    "duplicate_doi",
    "duplicate_arxiv_id",
}


def _display_year(record: dict[str, Any]) -> str:
    preprint = record.get("first_preprint_date", "")
    publication = record.get("publication_date", "")
    if preprint[:4].isdigit():
        return preprint[:4]
    if publication[:4].isdigit():
        return publication[:4]
    years = re.findall(r"\b(?:19|20)\d{2}\b", record.get("legacy_text", ""))
    return years[-1] if years else "Undated"


def _legacy_sort_key(record: dict[str, Any]) -> tuple[int, int]:
    return record.get("legacy_order", 0), int(record["ref_id"][3:])


def sorted_active_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active = [record for record in records if not record.get("duplicate_of")]
    return sorted(active, key=_legacy_sort_key, reverse=True)


def blocking_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if not record.get("duplicate_of") and (
            record.get("review_status") != "accepted"
            or BLOCKING_ISSUES.intersection(record.get("issues", []))
        )
    ]


def _authors_text(record: dict[str, Any]) -> str:
    authors = [author.get("display", "").strip() for author in record.get("authors", [])]
    return ", ".join(author for author in authors if author)


def _control(*,
             label: str,
             url: str,
             unavailable_label: str,
             class_name: str) -> str:
    if url:
        return (
            f'<a class="publication-control {class_name}" '
            f'href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">'
            f"{html.escape(label)}</a>"
        )
    return (
        '<span class="publication-control publication-control--missing" '
        f'aria-disabled="true">{html.escape(unavailable_label)}</span>'
    )


def _render_entry(record: dict[str, Any],
                  *,
                  draft: bool) -> str:
    title = record.get("title") or record.get("legacy_text") or record["ref_id"]
    authors = _authors_text(record) or "Authors unresolved"
    citation = record.get("citation", "")
    doi = record.get("doi", "")
    doi_markup = (
        f'DOI: <a href="https://doi.org/{html.escape(doi, quote=True)}" '
        f'target="_blank" rel="noopener">https://doi.org/{html.escape(doi)}</a>'
        if doi else "DOI:"
    )
    file_data = record.get("file", {})
    file_kind = file_data.get("kind", "PDF") or "PDF"
    file_control = _control(
        label=file_kind,
        url=file_data.get("dropbox_url", ""),
        unavailable_label=f"{file_kind} unavailable",
        class_name="publication-control--file",
    )
    webpage_control = _control(
        label="Webpage",
        url=record.get("webpage_url", ""),
        unavailable_label="Webpage unavailable",
        class_name="publication-control--webpage",
    )
    review_markup = ""
    if draft and record.get("review_status") != "accepted":
        issues = ", ".join(record.get("issues", [])) or "metadata review required"
        review_markup = (
            '<div class="publication-review-note">Draft review: '
            f"{html.escape(issues)}</div>"
        )
    return "\n".join([
        f'<article class="experimental-publication" id="{record["ref_id"]}" '
        f'data-ref="{record["ref_id"]}">',
        f'  <div class="experimental-publication-title"><strong>{html.escape(title)}</strong></div>',
        f'  <div class="experimental-publication-authors">{html.escape(authors)}</div>',
        f'  <div class="experimental-publication-citation">{html.escape(citation)}</div>',
        f'  <div class="experimental-publication-doi">{doi_markup}</div>',
        '  <div class="experimental-publication-controls">',
        f"    {file_control}",
        f"    {webpage_control}",
        "  </div>",
        f"  {review_markup}" if review_markup else "",
        "</article>",
    ]).replace("\n\n</article>", "\n</article>")


def render_list(database: dict[str, Any],
                *,
                draft: bool) -> str:
    records = sorted_active_records(database["records"])
    entries = "\n".join(_render_entry(record, draft=draft) for record in records)
    return f'<div class="publication-year-list">{entries}</div>\n'


def render_page(*,
                draft: bool,
                unresolved_count: int,
                list_filename: str,
                stylesheet_filename: str) -> str:
    banner_markup = ""
    if draft:
        banner_markup = (
            '        <div class="experimental-draft-banner" role="status">'
            f"Draft migration: {unresolved_count} records still have review items."
            "</div>\n"
        )
    robots_meta = (
        '    <meta name="robots" content="noindex, nofollow" />\n'
        if draft else ""
    )
    title = "Draft Publications" if draft else "Publications"
    return f'''<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
{robots_meta}    <title>{title}</title>
    <link rel="stylesheet" href="assets/styles.css" />
    <link rel="stylesheet" href="assets/{stylesheet_filename}" />
    <script>
      window.MathJax = {{ tex: {{ inlineMath: [["\\\\(", "\\\\)"]] }} }};
    </script>
    <script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
  </head>
  <body>
    <div id="site-header"></div>
    <main>
      <section class="experimental-publications-section">
        <h1>Publications</h1>
{banner_markup}        <p class="experimental-publications-note">
          For a complete and up-to-date list, see the
          <a href="https://scholar.google.com/citations?user=0qjME1gAAAAJ" target="_blank" rel="noopener">
            Google Scholar
          </a>.
        </p>
        <div id="experimental-publications-list" aria-live="polite"></div>
      </section>
    </main>
    <footer>© 2025 Demler group; original design by I. Demler</footer>
    <script>
      Promise.all([
        fetch("header.html").then((response) => response.text()),
        fetch("{list_filename}", {{ cache: "no-cache" }}).then((response) => response.text())
      ]).then(([headerHtml, publicationsHtml]) => {{
        const header = document.getElementById("site-header");
        const publicationsList = document.getElementById("experimental-publications-list");
        header.innerHTML = headerHtml;
        publicationsList.innerHTML = publicationsHtml;
        header.querySelectorAll("a").forEach((link) => {{
          if ((link.getAttribute("href") || "").includes("publications")) {{
            link.classList.add("active");
          }}
        }});
        if (window.MathJax && MathJax.typesetPromise) {{
          MathJax.typesetPromise([publicationsList]);
        }}
      }}).catch((error) => {{
        document.getElementById("experimental-publications-list").textContent =
          `Unable to load publications: ${{error.message}}`;
      }});
    </script>
  </body>
</html>
'''


def render_stylesheet() -> str:
    return '''.experimental-publications-section {
  max-width: 980px;
  margin: 0 auto;
}

.experimental-publications-section h1 {
  margin-top: 0;
}

.experimental-publications-note {
  color: #526275;
  margin-bottom: 28px;
}

.experimental-draft-banner {
  padding: 12px 16px;
  margin: 0 0 18px;
  color: #633c00;
  background: #fff3d8;
  border: 1px solid #e6c36c;
  border-radius: 8px;
}

.publication-year {
  margin-bottom: 44px;
}

.publication-year-title {
  position: sticky;
  top: 0;
  z-index: 1;
  margin: 0 0 14px;
  padding: 8px 0;
  font-size: 28px;
  color: #0d3f6d;
  background: rgba(255, 255, 255, 0.96);
  border-bottom: 2px solid #d4deef;
}

.publication-year-list {
  display: block;
}

.experimental-publication {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas:
    "title title"
    "authors authors"
    "citation controls"
    "doi controls";
  column-gap: 16px;
  padding: 12px 0 14px;
  border-bottom: 1px solid #d4deef;
}

.experimental-publication:first-child {
  padding-top: 0;
}

.experimental-publication-title {
  grid-area: title;
  font-size: 20px;
  line-height: 1.3;
  color: #0f1b2b;
}

.experimental-publication-authors {
  grid-area: authors;
  margin-top: 2px;
  font-size: 16px;
  line-height: 1.35;
  color: #425776;
}

.experimental-publication-citation,
.experimental-publication-doi {
  font-size: 15px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.experimental-publication-citation {
  grid-area: citation;
  margin-top: 4px;
}

.experimental-publication-doi {
  grid-area: doi;
}

.experimental-publication-doi a {
  color: #1f4f87;
}

.experimental-publication-controls {
  grid-area: controls;
  display: flex;
  flex-wrap: wrap;
  align-self: center;
  justify-self: end;
  gap: 9px;
}

.publication-control {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 5px 13px;
  font-size: 15px;
  font-weight: 700;
  line-height: 1;
  text-decoration: none;
  border-radius: 999px;
}

.publication-control--file {
  color: #fff;
  background: #0d3f6d;
}

.publication-control--webpage {
  color: #0d3f6d;
  background: #e5edfa;
  border: 1px solid #b7c9e5;
}

.publication-control--missing {
  color: #6f7883;
  background: #eef1f4;
  border: 1px solid #d5dbe1;
  cursor: not-allowed;
}

.publication-review-note {
  margin-top: 12px;
  padding-top: 9px;
  font-size: 14px;
  color: #8a4d00;
  border-top: 1px dashed #e1bf7b;
}

@media (max-width: 720px) {
  .publication-year-title {
    position: static;
  }

  .experimental-publication {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas:
      "title"
      "authors"
      "citation"
      "doi"
      "controls";
    padding: 11px 0 13px;
  }

  .experimental-publication-title {
    font-size: 18px;
  }

  .experimental-publication-controls {
    justify-self: start;
    margin-top: 7px;
  }
}
'''


def _bibtex_escape(value: str) -> str:
    return value.replace("\\(", "$").replace("\\)", "$")


def render_bibtex(records: list[dict[str, Any]]) -> str:
    entries: list[str] = []
    for record in sorted_active_records(records):
        fields: list[tuple[str, str]] = []
        title = record.get("title", "")
        authors = " and ".join(
            author.get("display", "") for author in record.get("authors", [])
            if author.get("display", "")
        )
        year = _display_year(record)
        if title:
            fields.append(("title", title))
        if authors:
            fields.append(("author", authors))
        if record.get("venue"):
            fields.append(("journal", record["venue"]))
        if record.get("volume"):
            fields.append(("volume", record["volume"]))
        if record.get("pages"):
            fields.append(("pages", record["pages"]))
        if year.isdigit():
            fields.append(("year", year))
        if record.get("doi"):
            fields.append(("doi", record["doi"]))
        if record.get("arxiv_id"):
            fields.extend([
                ("eprint", record["arxiv_id"]),
                ("archivePrefix", "arXiv"),
            ])
        if record.get("webpage_url"):
            fields.append(("url", record["webpage_url"]))
        if record.get("citation") and not record.get("venue"):
            fields.append(("note", record["citation"]))
        lines = [f"@article{{{record['ref_id']},"]
        for field_index, (name, value) in enumerate(fields):
            comma = "," if field_index < len(fields) - 1 else ""
            lines.append(f"  {name} = {{{_bibtex_escape(value)}}}{comma}")
        lines.append("}")
        entries.append("\n".join(lines))
    return "\n\n".join(entries) + "\n"


def write_outputs(database: dict[str, Any],
                  *,
                  repository_root: Path,
                  draft: bool) -> None:
    unresolved = blocking_records(database["records"])
    if unresolved and not draft:
        refs = ", ".join(record["ref_id"] for record in unresolved[:12])
        suffix = "..." if len(unresolved) > 12 else ""
        raise RuntimeError(
            f"Cannot render clean output: {len(unresolved)} records need review ({refs}{suffix})"
        )
    output_prefix = "publications_experimental" if draft else "publications"
    list_path = repository_root / f"{output_prefix}_list.html"
    page_path = repository_root / f"{output_prefix}.html"
    stylesheet_filename = (
        "publications-experimental.css" if draft else "publications.css"
    )
    stylesheet_path = repository_root / "assets" / stylesheet_filename
    bibtex_path = repository_root / f"{output_prefix}.bib"

    list_path.write_text(
        render_list(database, draft=draft),
        encoding="utf-8",
    )
    page_path.write_text(
        render_page(
            draft=draft,
            unresolved_count=len(unresolved),
            list_filename=list_path.name,
            stylesheet_filename=stylesheet_filename,
        ),
        encoding="utf-8",
    )
    stylesheet_path.write_text(
        render_stylesheet(),
        encoding="utf-8",
    )
    bibtex_path.write_text(
        render_bibtex(database["records"]),
        encoding="utf-8",
    )
