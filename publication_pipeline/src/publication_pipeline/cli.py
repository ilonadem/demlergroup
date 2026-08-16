from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from .corpus import (
    merge_corpus,
    scan_local_corpus,
)
from .database import (
    apply_overrides,
    detect_identity_collisions,
    save_database,
)
from .dropbox_api import (
    DEFAULT_CREDENTIALS_PATH,
    DropboxClient,
    apply_link_manifest,
    authorize_dropbox,
    plan_links,
)
from .metadata import MetadataClient, enrich_database, write_review_reports
from .render import write_outputs
from .util import read_json, write_json
from .validate import (
    check_live_links,
    validate_database,
    validate_generated_list,
    write_check_report,
)


PACKAGE_PATH = Path(__file__).resolve()
PIPELINE_ROOT = PACKAGE_PATH.parents[2]
REPOSITORY_ROOT = PACKAGE_PATH.parents[3]
DATABASE_PATH = PIPELINE_ROOT / "data" / "publications.json"
OVERRIDES_PATH = PIPELINE_ROOT / "data" / "overrides.json"
WORK_DIRECTORY = PIPELINE_ROOT / "work"
DEFAULT_LOCAL_DROPBOX = (
    Path.home() / "Library" / "CloudStorage" / "Dropbox" / "PUBLICATIONS (1)"
)


def _local_dropbox_path() -> Path:
    return Path(os.environ.get("PUBLICATIONS_DROPBOX_LOCAL_PATH", DEFAULT_LOCAL_DROPBOX))


def _remote_dropbox_path() -> str:
    return os.environ.get("DROPBOX_PUBLICATIONS_PATH", "/PUBLICATIONS (1)")


def _load_database(*,
                   apply_manual_overrides: bool = True) -> dict[str, Any]:
    database = read_json(DATABASE_PATH)
    if not database:
        raise RuntimeError("Canonical publication database is missing from this checkout.")
    return apply_overrides(database, OVERRIDES_PATH) if apply_manual_overrides else database


def _record_identity_collisions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    collision_issues = {
        "duplicate_doi",
        "duplicate_arxiv_id",
        "near_duplicate_title",
    }
    for record in records:
        record["issues"] = [
            issue for issue in record.get("issues", [])
            if issue not in collision_issues
        ]
    collisions = detect_identity_collisions(records)
    by_ref = {record["ref_id"]: record for record in records}
    for collision in collisions:
        for ref_id in collision["ref_ids"]:
            record = by_ref[ref_id]
            if collision["kind"] not in record["issues"]:
                record["issues"].append(collision["kind"])
            record["review_status"] = "needs_review"
    return collisions


def command_sync(arguments: argparse.Namespace) -> None:
    crossref_mailto = os.environ.get("CROSSREF_MAILTO", "")
    if not crossref_mailto:
        raise RuntimeError(
            "CROSSREF_MAILTO is required. Set it to a monitored contact email before sync."
        )
    database = _load_database()
    inventory = scan_local_corpus(
        _local_dropbox_path(),
        hash_files=arguments.hash_files,
    )
    merge_corpus(database["records"], inventory)
    client = MetadataClient(
        WORK_DIRECTORY / "cache",
        crossref_mailto=crossref_mailto,
    )
    database = enrich_database(
        database,
        corpus_folder=_local_dropbox_path(),
        client=client,
        search_arxiv=arguments.search_arxiv,
        maximum_records=arguments.maximum_records,
    )
    database = apply_overrides(database, OVERRIDES_PATH)
    database["audit"]["ignored_variants"] = inventory["ignored_variants"]
    database["audit"]["unrecognized_files"] = inventory["unrecognized"]
    database["audit"]["identity_collisions"] = _record_identity_collisions(
        database["records"]
    )
    save_database(DATABASE_PATH, database)
    review_count = write_review_reports(
        database,
        json_path=WORK_DIRECTORY / "review.json",
        html_path=WORK_DIRECTORY / "review.html",
    )
    print(f"Metadata sync complete; {review_count} records have review notes.")


def command_auth_dropbox(arguments: argparse.Namespace) -> None:
    path = authorize_dropbox(arguments.app_key,
                             credentials_path=Path(arguments.credentials))
    print(f"Dropbox credentials saved to {path}")


def command_plan_links(arguments: argparse.Namespace) -> None:
    database = _load_database()
    client = DropboxClient.from_credentials(Path(arguments.credentials))
    manifest = plan_links(
        database,
        client=client,
        remote_folder=arguments.remote_folder,
    )
    output = Path(arguments.output)
    write_json(output, manifest)
    creation_count = sum(entry["action"] == "create" for entry in manifest["entries"])
    reuse_count = sum(entry["action"] == "reuse" for entry in manifest["entries"])
    print(
        f"Wrote {output}: {creation_count} proposed creations, {reuse_count} reusable links."
    )


def command_apply_links(arguments: argparse.Namespace) -> None:
    database = _load_database()
    manifest = read_json(Path(arguments.manifest))
    client = DropboxClient.from_credentials(Path(arguments.credentials))
    database = apply_link_manifest(database, manifest=manifest, client=client)
    save_database(DATABASE_PATH, database)
    print("Approved Dropbox link manifest applied.")


def command_render(arguments: argparse.Namespace) -> None:
    database = _load_database()
    write_outputs(database,
                  repository_root=REPOSITORY_ROOT,
                  draft=arguments.draft)
    mode = "draft" if arguments.draft else "clean"
    print(f"Generated {mode} publication HTML and BibTeX outputs.")


def command_check(arguments: argparse.Namespace) -> None:
    database = _load_database()
    errors = validate_database(database)
    generated_list = REPOSITORY_ROOT / "publications_list.html"
    if not generated_list.exists():
        errors.append("Publication list has not been rendered")
    else:
        errors.extend(validate_generated_list(database, generated_list))
    if arguments.live_links:
        errors.extend(check_live_links(
            database["records"],
            output_path=WORK_DIRECTORY / "link-check.json",
        ))
    write_check_report(WORK_DIRECTORY / "check.json", errors=errors)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    print("All publication-pipeline checks passed.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser("sync", help="Refresh corpus and bibliographic metadata")
    sync.add_argument("--hash-files", action="store_true")
    sync.add_argument("--search-arxiv", action="store_true")
    sync.add_argument("--maximum-records", type=int)
    sync.set_defaults(handler=command_sync)

    auth = subparsers.add_parser("auth-dropbox", help="Authorize the Dropbox API app")
    auth.add_argument("--app-key", required=True)
    auth.add_argument("--credentials", default=str(DEFAULT_CREDENTIALS_PATH))
    auth.set_defaults(handler=command_auth_dropbox)

    link_plan = subparsers.add_parser("plan-links", help="Create a non-mutating link plan")
    link_plan.add_argument("--credentials", default=str(DEFAULT_CREDENTIALS_PATH))
    link_plan.add_argument("--remote-folder", default=_remote_dropbox_path())
    link_plan.add_argument("--output", default=str(WORK_DIRECTORY / "link-plan.json"))
    link_plan.set_defaults(handler=command_plan_links)

    apply_links = subparsers.add_parser("apply-links", help="Apply an approved link plan")
    apply_links.add_argument("--manifest", required=True)
    apply_links.add_argument("--credentials", default=str(DEFAULT_CREDENTIALS_PATH))
    apply_links.set_defaults(handler=command_apply_links)

    render = subparsers.add_parser("render", help="Generate publication HTML and BibTeX")
    render.add_argument("--draft", action="store_true")
    render.set_defaults(handler=command_render)

    check = subparsers.add_parser("check", help="Validate data and generated outputs")
    check.add_argument("--live-links", action="store_true")
    check.set_defaults(handler=command_check)
    return parser


def main() -> None:
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        arguments.handler(arguments)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
