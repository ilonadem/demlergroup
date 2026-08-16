from pathlib import Path

from publication_pipeline.corpus import (
    detect_document_mismatch,
    find_content_collisions,
    scan_local_corpus,
)


def test_primary_file_selection_and_ignored_variants(tmp_path: Path):
    for filename, contents in (
        ("ref10.pdf", b"main"),
        ("ref10.ps", b"old"),
        ("ref10_supp.pdf", b"supp"),
        ("ref71a.pdf", b"alias"),
        ("ref71b.pdf", b"reply"),
        ("notes.docx", b"notes"),
    ):
        (tmp_path / filename).write_bytes(contents)
    inventory = scan_local_corpus(tmp_path, hash_files=True)
    assert inventory["selected"]["ref10"]["filename"] == "ref10.pdf"
    assert inventory["selected"]["ref71"]["filename"] == "ref71a.pdf"
    assert {item["filename"] for item in inventory["ignored_variants"]} == {
        "ref10.ps",
        "ref10_supp.pdf",
        "ref71b.pdf",
    }
    assert inventory["unrecognized"] == ["notes.docx"]


def test_content_collisions_are_reported_not_merged():
    records = [
        {"ref_id": "ref1", "file": {"sha256": "same"}},
        {"ref_id": "ref2", "file": {"sha256": "same"}},
    ]
    assert find_content_collisions(records) == [
        {"sha256": "same", "ref_ids": ["ref1", "ref2"]}
    ]


def test_document_mismatch_requires_conflicting_prominent_identifier():
    record = {
        "title": "Expected publication title",
        "doi": "",
        "arxiv_id": "2501.05562",
    }
    assert detect_document_mismatch(
        record,
        "Different title\narXiv:2501.16856v1 [cond-mat]",
    )
    assert not detect_document_mismatch(
        record,
        "A revised title\narXiv:2501.05562v2 [cond-mat]",
    )
    assert not detect_document_mismatch(record, "Garbled PostScript extraction")
