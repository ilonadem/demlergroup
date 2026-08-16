from copy import deepcopy

import pytest

from publication_pipeline.dropbox_api import apply_link_manifest, plan_links


class FakeDropboxClient:
    def __init__(self):
        self.created = []

    def list_folder(self, path):
        return [
            {
                ".tag": "file",
                "name": "ref1.pdf",
                "path_lower": f"{path.casefold()}/ref1.pdf",
                "content_hash": "abc",
            },
            {
                ".tag": "file",
                "name": "ref2.ps",
                "path_lower": f"{path.casefold()}/ref2.ps",
                "content_hash": "def",
            },
        ]

    def list_shared_links(self, path):
        if path.endswith("ref1.pdf"):
            return [{"url": "https://dropbox.example/ref1"}]
        return []

    def create_shared_link(self, path):
        self.created.append(path)
        return {"url": f"https://dropbox.example{path}"}


def database_fixture():
    return {
        "records": [
            {
                "ref_id": "ref1",
                "file": {"filename": "ref1.pdf", "dropbox_url": "", "link_status": "unlinked"},
            },
            {
                "ref_id": "ref2",
                "file": {"filename": "ref2.ps", "dropbox_url": "", "link_status": "unlinked"},
            },
        ]
    }


def test_wrong_file_is_never_planned_for_sharing():
    client = FakeDropboxClient()
    database = database_fixture()
    database["records"][0]["issues"] = ["wrong_file"]
    manifest = plan_links(database, client=client, remote_folder="/PUBLICATIONS")
    assert manifest["entries"][0]["action"] == "blocked_review"


def test_plan_is_non_mutating_and_reuses_existing_links():
    client = FakeDropboxClient()
    database = database_fixture()
    original = deepcopy(database)
    manifest = plan_links(database, client=client, remote_folder="/PUBLICATIONS")
    assert database == original
    assert [entry["action"] for entry in manifest["entries"]] == ["reuse", "create"]
    assert manifest["approved"] is False
    assert client.created == []


def test_apply_requires_approval_and_unchanged_digest():
    client = FakeDropboxClient()
    manifest = plan_links(database_fixture(), client=client, remote_folder="/PUBLICATIONS")
    with pytest.raises(ValueError, match="not approved"):
        apply_link_manifest(database_fixture(), manifest=manifest, client=client)
    manifest["approved"] = True
    manifest["entries"][0]["filename"] = "tampered.pdf"
    with pytest.raises(ValueError, match="contents changed"):
        apply_link_manifest(database_fixture(), manifest=manifest, client=client)


def test_approved_manifest_creates_only_missing_links():
    client = FakeDropboxClient()
    database = database_fixture()
    manifest = plan_links(database, client=client, remote_folder="/PUBLICATIONS")
    manifest["approved"] = True
    updated = apply_link_manifest(database, manifest=manifest, client=client)
    assert client.created == ["/publications/ref2.ps"]
    assert updated["records"][0]["file"]["dropbox_url"] == "https://dropbox.example/ref1"
    assert updated["records"][1]["file"]["link_status"] == "linked"
