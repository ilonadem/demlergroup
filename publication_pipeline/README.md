# Publication pipeline

This project maintains the structured publication database from the synced
Dropbox paper folder and generates the website's publication HTML and BibTeX
outputs. The pre-migration page remains recoverable through Git history.

## Prerequisites

- `uv`
- Poppler's `pdftotext` and Ghostscript's `ps2ascii`
- The synced Dropbox folder (default:
  `~/Library/CloudStorage/Dropbox/PUBLICATIONS (1)`)
- `CROSSREF_MAILTO` for Crossref enrichment
- A Full Dropbox API app with `files.metadata.read`, `sharing.read`, and
  `sharing.write` for link creation

Paths may be overridden with `PUBLICATIONS_DROPBOX_LOCAL_PATH` and
`DROPBOX_PUBLICATIONS_PATH`.

## Workflow

```bash
cd publication_pipeline
uv run pubs sync
uv run pubs plan-links
# Inspect work/link-plan.json and change only "approved" to true.
uv run pubs apply-links --manifest work/link-plan.json
uv run pubs render
uv run pubs check --live-links
```

`sync` scans local files and enriches the canonical records through Crossref
and arXiv, using an ignored response cache. Records that cannot be matched
safely are written to `work/review.json` and `work/review.html`; corrections
belong in `data/overrides.json`.

A canonical file whose identifier immediately follows the current database,
such as `ref456.pdf` after `ref455`, is imported automatically. Multiple new
files may be added together when their identifiers are consecutive. A gap is
rejected instead of silently assigning or skipping an identity. New arXiv
preprints receive an `arXiv:NNNN.NNNNN` citation automatically; exact DOI
metadata supplies a concise journal citation for published papers.

If `plan-links` reports `missing_remote` for a newly added local file, wait for
the Dropbox desktop client to finish uploading it and generate a fresh plan.
Do not approve or apply the stale manifest.

Clean rendering writes `publications.html`, `publications_list.html`,
`assets/publications.css`, and `publications.bib`. Publications preserve the
exact display order of the old website. Publication and first-preprint dates
are metadata and never change that order.

For inspection before the review queue is empty:

```bash
uv run pubs render --draft
```

Draft rendering writes ignored `publications_experimental*` preview files and
does not replace the production page.

## Dropbox authorization

Create a Full Dropbox app, enable the three scopes above, and run:

```bash
uv run pubs auth-dropbox --app-key YOUR_APP_KEY
```

The command uses OAuth with PKCE. The refresh token is written with mode 0600
to `~/Library/Application Support/demler-publications/credentials.json`, never
inside this repository. Link planning is non-mutating. Link creation requires
an approved manifest whose digest still matches its contents.

## Safety properties

- `refNNN` identifiers never change.
- Newly discovered identifiers must continue the existing sequence.
- The generated list preserves the old website's publication order.
- Existing links are reused and never revoked or modified.
- Duplicate identities and duplicate file content are reported, not merged.
- Normal rendering stops while bibliographic review items remain.
- `check` validates the canonical database and generated production list.
