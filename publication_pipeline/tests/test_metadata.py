from publication_pipeline.metadata import (
    _apply_crossref,
    _blocking_issues,
    _candidate_score,
    _crossref_date,
    _parse_arxiv_entry,
)
import xml.etree.ElementTree as ET


def test_crossref_candidate_requires_demler_and_matching_year():
    record = {
        "title": "Theory of the Resonant Neutron Scattering of High-Temperature Superconductors",
        "legacy_text": (
            "E. Demler and S.C. Zhang, Theory of the Resonant Neutron Scattering "
            "of High-Temperature Superconductors, Phys. Rev. Lett. 75:4126 (1995)"
        ),
        "publication_date": "1995",
    }
    candidate = {
        "title": ["Theory of the Resonant Neutron Scattering of High-Temperature Superconductors"],
        "author": [
            {"given": "Eugene", "family": "Demler"},
            {"given": "Shou-Cheng", "family": "Zhang"},
        ],
        "issued": {"date-parts": [[1995]]},
    }
    assert _candidate_score(record, candidate) == 100.0
    candidate["author"] = [{"given": "Someone", "family": "Else"}]
    assert _candidate_score(record, candidate) == 0.0


def test_arxiv_fixture_parsing_strips_version():
    entry = ET.fromstring(
        '<entry xmlns="http://www.w3.org/2005/Atom">'
        "<id>https://arxiv.org/abs/2601.18712v2</id>"
        "<published>2026-01-27T12:00:00Z</published>"
        "<title>  Example   title </title>"
        "<author><name>Eugene Demler</name></author>"
        "</entry>"
    )
    parsed = _parse_arxiv_entry(entry)
    assert parsed["arxiv_id"] == "2601.18712"
    assert parsed["published"] == "2026-01-27"
    assert parsed["title"] == "Example title"


def test_old_style_arxiv_fixture_preserves_archive_name():
    entry = ET.fromstring(
        '<entry xmlns="http://www.w3.org/2005/Atom">'
        "<id>https://arxiv.org/abs/cond-mat/0106645v2</id>"
        "<published>2001-06-29T12:00:00Z</published>"
        "<title>Fermions and Bosons in Superconducting Amorphous Wires</title>"
        "</entry>"
    )
    parsed = _parse_arxiv_entry(entry)
    assert parsed["arxiv_id"] == "cond-mat/0106645"


def test_discarded_document_arxiv_and_api_errors_do_not_block():
    record = {
        "issues": ["discarded_document_arxiv", "metadata_error:HTTPError"]
    }
    assert _blocking_issues(record) == []


def test_crossref_date_uses_original_publication_not_later_digitization():
    item = {
        "published-online": {"date-parts": [[2012, 5, 1]]},
        "issued": {"date-parts": [[1996, 7, 30]]},
    }
    assert _crossref_date(item) == ("1996-07-30", "day")
