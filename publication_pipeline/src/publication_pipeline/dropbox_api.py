from __future__ import annotations

import base64
import hashlib
import json
import secrets
import stat
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .util import read_json, sha256_bytes, write_json


DROPBOX_AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
DROPBOX_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
DROPBOX_API_ROOT = "https://api.dropboxapi.com/2"
DEFAULT_CREDENTIALS_PATH = (
    Path.home() / "Library" / "Application Support" /
    "demler-publications" / "credentials.json"
)


class DropboxClient:
    def __init__(self,
                 *,
                 app_key: str,
                 refresh_token: str):
        self.app_key = app_key
        self.refresh_token = refresh_token
        self._access_token = ""

    @classmethod
    def from_credentials(cls,
                         path: Path = DEFAULT_CREDENTIALS_PATH) -> "DropboxClient":
        credentials = read_json(path)
        if not credentials:
            raise RuntimeError(
                f"Dropbox credentials not found at {path}. Run pubs auth-dropbox first."
            )
        return cls(app_key=credentials["app_key"],
                   refresh_token=credentials["refresh_token"])

    def list_folder(self,
                    path: str) -> list[dict[str, Any]]:
        response = self._api("files/list_folder", {"path": path, "recursive": False})
        entries = response.get("entries", [])
        while response.get("has_more"):
            response = self._api(
                "files/list_folder/continue",
                {"cursor": response["cursor"]},
            )
            entries.extend(response.get("entries", []))
        return [entry for entry in entries if entry.get(".tag") == "file"]

    def list_shared_links(self,
                          path: str) -> list[dict[str, Any]]:
        response = self._api(
            "sharing/list_shared_links",
            {"path": path, "direct_only": True},
        )
        return response.get("links", [])

    def create_shared_link(self,
                           path: str) -> dict[str, Any]:
        try:
            return self._api(
                "sharing/create_shared_link_with_settings",
                {
                    "path": path,
                    "settings": {"requested_visibility": "public"},
                },
            )
        except DropboxApiError as error:
            if "shared_link_already_exists" not in error.body:
                raise
            links = self.list_shared_links(path)
            if not links:
                raise
            return links[0]

    def _refresh_access_token(self) -> None:
        body = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.app_key,
        }).encode("utf-8")
        request = urllib.request.Request(DROPBOX_TOKEN_URL, data=body, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self._access_token = payload["access_token"]

    def _api(self,
             endpoint: str,
             payload: dict[str, Any]) -> dict[str, Any]:
        if not self._access_token:
            self._refresh_access_token()
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{DROPBOX_API_ROOT}/{endpoint}",
            data=body,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            if error.code == 401:
                self._access_token = ""
            raise DropboxApiError(error.code, body) from error


class DropboxApiError(RuntimeError):
    def __init__(self,
                 status_code: int,
                 body: str):
        super().__init__(f"Dropbox API returned HTTP {status_code}: {body}")
        self.status_code = status_code
        self.body = body


def authorize_dropbox(app_key: str,
                      *,
                      credentials_path: Path = DEFAULT_CREDENTIALS_PATH) -> Path:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    parameters = {
        "client_id": app_key,
        "response_type": "code",
        "token_access_type": "offline",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    authorization_url = f"{DROPBOX_AUTH_URL}?{urllib.parse.urlencode(parameters)}"
    print("Open this URL, approve access, and paste the authorization code below:\n")
    print(authorization_url)
    authorization_code = input("\nAuthorization code: ").strip()
    token_body = urllib.parse.urlencode({
        "code": authorization_code,
        "grant_type": "authorization_code",
        "client_id": app_key,
        "code_verifier": verifier,
    }).encode("utf-8")
    request = urllib.request.Request(DROPBOX_TOKEN_URL, data=token_body, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        tokens = json.loads(response.read().decode("utf-8"))
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("Dropbox did not return a refresh token")
    credentials_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(credentials_path, {"app_key": app_key, "refresh_token": refresh_token})
    credentials_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return credentials_path


def _manifest_digest(entries: list[dict[str, Any]]) -> str:
    canonical = json.dumps(entries,
                           ensure_ascii=True,
                           sort_keys=True,
                           separators=(",", ":"))
    return sha256_bytes(canonical.encode("utf-8"))


def plan_links(database: dict[str, Any],
               *,
               client: DropboxClient,
               remote_folder: str) -> dict[str, Any]:
    remote_entries = client.list_folder(remote_folder)
    remote_by_name = {
        entry["name"].casefold(): entry
        for entry in remote_entries
    }
    entries: list[dict[str, Any]] = []
    for record in database["records"]:
        filename = record.get("file", {}).get("filename", "")
        if "wrong_file" in record.get("issues", []):
            entries.append({
                "ref_id": record["ref_id"],
                "filename": filename,
                "remote_path": "",
                "action": "blocked_review",
                "existing_url": "",
            })
            continue
        if not filename:
            entries.append({
                "ref_id": record["ref_id"],
                "filename": "",
                "remote_path": "",
                "action": "missing",
                "existing_url": "",
            })
            continue
        remote = remote_by_name.get(filename.casefold())
        if not remote:
            entries.append({
                "ref_id": record["ref_id"],
                "filename": filename,
                "remote_path": "",
                "action": "missing_remote",
                "existing_url": "",
            })
            continue
        path = remote.get("path_lower") or remote.get("path_display")
        links = client.list_shared_links(path)
        entries.append({
            "ref_id": record["ref_id"],
            "filename": filename,
            "remote_path": path,
            "content_hash": remote.get("content_hash", ""),
            "action": "reuse" if links else "create",
            "existing_url": links[0].get("url", "") if links else "",
        })
    return {
        "schema_version": 1,
        "approved": False,
        "remote_folder": remote_folder,
        "entries_digest": _manifest_digest(entries),
        "entries": entries,
    }


def apply_link_manifest(database: dict[str, Any],
                        *,
                        manifest: dict[str, Any],
                        client: DropboxClient) -> dict[str, Any]:
    if manifest.get("approved") is not True:
        raise ValueError("Link manifest is not approved")
    entries = manifest.get("entries", [])
    expected_digest = _manifest_digest(entries)
    if manifest.get("entries_digest") != expected_digest:
        raise ValueError("Link manifest contents changed after planning")

    records = {record["ref_id"]: record for record in database["records"]}
    for entry in entries:
        record = records[entry["ref_id"]]
        action = entry["action"]
        if action == "reuse":
            url = entry["existing_url"]
        elif action == "create":
            link = client.create_shared_link(entry["remote_path"])
            url = link["url"]
        elif action in {"blocked_review", "missing", "missing_remote"}:
            continue
        else:
            raise ValueError(f"Unknown link-manifest action: {action}")
        record["file"]["dropbox_url"] = url
        record["file"]["link_status"] = "linked"
        if entry.get("content_hash"):
            record["file"]["dropbox_content_hash"] = entry["content_hash"]
    return database
