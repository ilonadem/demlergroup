---
name: demler-publication-ingest
description: Ingest or update a Demler group website publication from a Dropbox PDF link and BibTeX entry, preserving stable refNNN identifiers and updating publications-legacy.html with clean citation and badge links for arXiv, PDF, and journal versions.
---

# Demler Publication Ingest

Use this skill in the Demler group website repo when the user provides a Dropbox PDF link plus a BibTeX entry and wants the publications page updated.

## Inputs

Expected inputs:
- A Dropbox PDF link, preferably view-only and pointing to `refNNN.pdf`.
- A BibTeX entry from the journal or arXiv.

If the Dropbox filename and the intended `refNNN` disagree, prefer the existing website `refNNN` when the paper is already listed. Ask only if the paper cannot be matched confidently.

## Workflow

1. Read local guidance first:
   - Read `KARPATHY.md` if present.
   - Read `.agents/ONBOARDING.md`.

2. Find whether the paper already exists:
   - Search `publications-legacy.html` for title words, DOI, arXiv ID, authors, and any `refNNN`.
   - If exactly one existing entry matches, update that entry in place.
   - If no entry matches, add a new entry near the chronological position used by the legacy list.
   - If multiple entries match, stop and ask which entry to update.

3. Preserve stable identifiers:
   - Treat `refNNN` as a stable paper/PDF identifier, not a chronological guarantee.
   - Do not relabel older publications to make numbering chronological.
   - For an existing paper, keep its current `refNNN` and use the Dropbox link for that file.

4. Render the citation from BibTeX:
   - Authors: `Given Family` order, comma-separated, using the names from BibTeX.
   - Title: use BibTeX title capitalization unless the target journal style clearly differs in the existing entry.
   - Preserve simple TeX title expressions, but convert inline BibTeX math delimiters from `$...$` to `\(...\)` before inserting into `publications-legacy.html`; `publications.html` uses MathJax to render title math.
   - Do not put TeX in badge labels, URLs, or image alt text.
   - Render modern entries as structured markup:
     `<li class="publication-entry">` containing `publication-title`, `publication-authors`, and `publication-links` blocks.
   - Render links as local text badges with `publication-badge`, not shields.io image badges.
   - Use an arXiv badge when BibTeX has `eprint`: `arXiv NNNN.NNNNN`, linked to `https://arxiv.org/abs/NNNN.NNNNN`.
   - Always use a PDF badge linked to the Dropbox URL.
   - When BibTeX has `doi`, add a journal/DOI badge linked to `https://doi.org/DOI`.
   - When BibTeX has `url` and it is distinct from the DOI URL and arXiv URL, add a journal/publisher badge linked to that URL.
   - Do not leave duplicate plain `DOI:` or `arXiv:` link blocks when converting an entry to badges.

5. Update `publications-legacy.html` surgically:
   - Replace only the matching entry's citation/PDF/DOI markup.
   - Keep the legacy `<hr>` and `<li>` structure.
   - Use the Dropbox URL exactly as provided unless only a harmless filename mismatch was corrected by the user.
   - Do not reformat unrelated publication entries.
   - After changing `publications-legacy.html`, bump `publicationsVersion` in `publications.html` to a fresh human-readable value such as `YYYY-MM-DD-refNNN` or `YYYY-MM-DD-publications`.
   - If publication CSS changed, bump the `assets/styles.css?v=...` query string in `publications.html` to the same value.

6. Verify:
   - Run `git diff --check`.
   - Confirm the updated title appears exactly once.
   - Confirm the old PDF URL for that entry is gone.
   - Confirm the new Dropbox URL appears exactly once.
   - Confirm the structured `publication-entry`, `publication-title`, `publication-authors`, and `publication-links` blocks are present for modern entries.
   - Confirm the arXiv badge link appears when `eprint` exists.
   - Confirm the DOI and BibTeX `url` badge links appear when applicable.
   - Confirm any inline title math uses `\(...\)` rather than raw `$...$`.
   - Confirm no duplicate plain DOI/arXiv link block remains after badge conversion.
   - Confirm `publicationsVersion` in `publications.html` was bumped when `publications-legacy.html` changed.
   - Confirm the stylesheet query string in `publications.html` was bumped when publication CSS changed.
   - If a local server is running, use `curl` or browser inspection to confirm the served page contains the update.

## Current repo convention

- The visible page is `publications.html`.
- It fetches `publications-legacy.html`, extracts `li` and `hr`, reverses them, and displays the result.
- Therefore, update `publications-legacy.html` unless the repository has since migrated to a generated data-file workflow.
