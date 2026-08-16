from pathlib import Path

from publication_pipeline.render import (
    render_list,
    render_page,
    render_stylesheet,
    sorted_active_records,
    write_outputs,
)
from publication_pipeline.validate import GeneratedListParser


def record(ref_id,
           year,
           *,
           legacy_order=None,
           preprint="",
           duplicate_of=""):
    return {
        "ref_id": ref_id,
        "legacy_order": legacy_order or int(ref_id[3:]),
        "title": f"Title {ref_id}",
        "authors": [{"display": "Eugene Demler"}],
        "citation": f"Journal ({year})",
        "doi": "",
        "arxiv_id": "",
        "first_preprint_date": preprint,
        "publication_date": str(year),
        "webpage_url": "",
        "file": {"kind": "PDF", "dropbox_url": ""},
        "review_status": "accepted",
        "issues": [],
        "duplicate_of": duplicate_of,
    }


def test_preserves_legacy_order_and_suppresses_confirmed_duplicates():
    records = [
        record("ref1", 2025, legacy_order=1, preprint="2026-02-01"),
        record("ref2", 2024, legacy_order=2),
        record("ref3", 2026, legacy_order=3, duplicate_of="ref2"),
    ]
    assert [item["ref_id"] for item in sorted_active_records(records)] == ["ref2", "ref1"]


def test_each_rendered_record_has_required_blocks_and_two_controls():
    database = {"records": [record("ref1", 2025), record("ref2", 2026)]}
    fragment = render_list(database, draft=False)
    parser = GeneratedListParser()
    parser.feed(fragment)
    assert parser.ref_ids == ["ref2", "ref1"]
    assert parser.title_count == 2
    assert parser.author_count == 2
    assert parser.citation_count == 2
    assert parser.doi_count == 2
    assert parser.control_count == 4
    assert fragment.count("DOI:</div>") == 2


def test_production_page_is_indexable_and_uses_production_assets():
    page = render_page(
        draft=False,
        unresolved_count=0,
        list_filename="publications_list.html",
        stylesheet_filename="publications.css",
    )
    assert 'name="robots"' not in page
    assert "<title>Publications</title>" in page
    assert 'href="assets/publications.css"' in page
    assert 'fetch("publications_list.html"' in page
    assert "Google Scholar" in page


def test_draft_page_is_noindex():
    page = render_page(
        draft=True,
        unresolved_count=2,
        list_filename="publications_experimental_list.html",
        stylesheet_filename="publications-experimental.css",
    )
    assert '<meta name="robots" content="noindex, nofollow" />' in page
    assert "Draft migration: 2 records still have review items." in page


def test_stylesheet_uses_compact_entries_without_cards():
    stylesheet = render_stylesheet()
    assert "grid-template-areas:" in stylesheet
    assert "border-bottom: 1px solid #d4deef;" in stylesheet
    assert "box-shadow" not in stylesheet


def test_draft_render_does_not_replace_production_outputs(tmp_path: Path):
    (tmp_path / "assets").mkdir()
    database = {"records": [record("ref1", 2025)]}
    write_outputs(database, repository_root=tmp_path, draft=False)
    production_page = (tmp_path / "publications.html").read_text(encoding="utf-8")

    write_outputs(database, repository_root=tmp_path, draft=True)

    assert (tmp_path / "publications.html").read_text(encoding="utf-8") == production_page
    assert (tmp_path / "publications_experimental.html").is_file()
    assert (tmp_path / "publications_experimental_list.html").is_file()
