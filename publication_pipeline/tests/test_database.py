from publication_pipeline.database import detect_identity_collisions


def test_detects_identifier_and_near_title_collisions():
    records = [
        {
            "ref_id": "ref1",
            "doi": "10.1000/example",
            "arxiv_id": "",
            "title": "Collective dynamics in a two-dimensional quantum magnet",
        },
        {
            "ref_id": "ref2",
            "doi": "10.1000/EXAMPLE",
            "arxiv_id": "",
            "title": "Collective dynamics in a two dimensional quantum magnet",
        },
    ]
    collisions = detect_identity_collisions(records)
    assert {collision["kind"] for collision in collisions} == {
        "duplicate_doi",
        "near_duplicate_title",
    }
