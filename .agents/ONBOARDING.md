# Demler Group Website Agent Onboarding

## Project shape

This repository is the static Demler group website. It is plain HTML/CSS plus static assets, with no package-managed build step.

Local preview:

```bash
python3 -m http.server 8000
```

Then open `http://localhost:8000`. Force-refresh if browser caching hides changes.

## Main files

- `KARPATHY.md` contains shared agent working guidelines for this repo.
- `publications.html` renders the publications page and fetches `publications-legacy.html`.
- `publications-legacy.html` contains the publication entries.
- `assets/styles.css` contains shared site styling, including modern publication entry styles.
- `header.html` contains shared navigation.

## Publication workflow

Use the repo skill at `.agents/skills/demler-publication-ingest/` when adding or updating a paper from a Dropbox PDF link plus BibTeX.

Current publication conventions:

- Keep `refNNN` stable; do not renumber old papers for chronology.
- Modern entries use structured markup: title, authors, and local text badges.
- Use badges for arXiv, PDF, and journal/DOI links when available.
- Convert inline BibTeX title math from `$...$` to `\(...\)`; MathJax renders it on `publications.html`.
- Bump `publicationsVersion` in `publications.html` whenever `publications-legacy.html` changes.
- If publication CSS changes, bump the `assets/styles.css?v=...` query string in `publications.html` too.

## Publication infrastructure status

Done:

- Added cache-busting for `publications-legacy.html` and the publications stylesheet in `publications.html`.
- Added MathJax rendering for publication-title TeX.
- Created the `$demler-publication-ingest` workflow for Dropbox link plus BibTeX ingestion.
- Piloted structured modern publication entries on `ref441` and `ref442`.

TODO:

- Migrate existing publication records to the structured entry format with local badges.
- Create a separate BibTeX database containing all publication entries.
- Sort generated HTML entries by the date when the first preprint appeared, not by `refNNN`.
- Split the publications page by year.
- Move publication PDFs and links toward one group-shared Dropbox location, then update website links consistently.

## Safety notes

- Do not commit Dropbox credentials, API tokens, private notes, or personal account details.
- Public Dropbox PDF links are fine to commit.
- Keep personal scratch notes in ignored local files, not in `.agents/`.
