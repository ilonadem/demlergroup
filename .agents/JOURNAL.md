# Agent Journal

## 2026-05-11

- Piloted cleaner publication formatting for `ref441` and `ref442`: separate title, authors, and local arXiv/PDF text badges.
- Added cache-busting for both `publications-legacy.html` and `assets/styles.css` from `publications.html`.
- Added conservative no-cache metadata on the publications page and no-cache fetch behavior for the legacy publication fragment.
- Updated the publication-ingest workflow so future publication changes bump cache versions and use the structured entry format.
- Moved stable agent scaffolding into committed `.agents/` files for future website maintainers.

## 2026-05-10

- Added a local knowledge-base scaffold for agent-facing project context.
- Marked `KARPATHY.md` as ignored local guidance for agents.
- Added and iterated a publication-ingest workflow: Dropbox PDF link plus BibTeX updates `publications-legacy.html` while preserving stable `refNNN` identifiers.
- Updated recent publications `ref429`, `ref441`, and `ref442` with Dropbox PDF links and badge/link controls.
- Added MathJax support on `publications.html` and converted the `ref441` title math from raw `$T_c$` to `\(T_c\)`.
- Diagnosed deployed-site confusion as browser caching.
