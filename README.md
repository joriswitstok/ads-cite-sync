# ADS references synchronisation

A GitHub Action that scans LaTeX file(s) for [ADS](https://ui.adsabs.harvard.edu/) bibcodes,
adds them to an ADS library, updates superseded (e.g. arXiv preprint) bibcodes in the LaTeX
source, and exports an up-to-date BibTeX `.bib` file — designed to run automatically whenever
an [Overleaf](https://www.overleaf.com/) project is synced to GitHub.

## How it works

The script scans `.tex` file(s) for strings matching the canonical 19-character ADS bibcode
format (e.g. `2026OJAp....955261W`). It then:

1. Adds all found bibcodes to a named ADS library (creating it if it does not exist).
2. Replaces any superseded bibcodes in the `.tex` file(s) by their canonical counterparts.
3. Fetches up-to-date BibTeX entries for all valid bibcodes from ADS.
4. Writes a `.bib` file and, optionally, commits the updated `.bib` and `.tex` file(s) back to
   the repository.

Because it scans for raw bibcodes rather than parsing citation commands, it works with any
LaTeX citation style, as long as bibcodes are used as BibTeX keys (the default when exporting
from ADS).

### Superseded bibcodes

When a preprint appears in a journal, ADS merges its arXiv record (e.g. `2025arXiv250918302P`)
into the published record (`2026A&A...712A.113P`), keeping the arXiv bibcode only as an
*alternate* bibcode. A `.tex` file citing the arXiv bibcode would then acquire a broken citation,
since the exported `.bib` file only contains the published entry.

The ADS library reveals this: only the canonical, published bibcode is stored there. Any cited
bibcode that is absent from the library after the update is therefore looked up on ADS (matching
on `identifier`, which also resolves alternate bibcodes), and where the canonical bibcode differs,
all occurrences in the scanned `.tex` file(s) are rewritten to it. Set `update_tex: false` to
disable this.

### Manually added entries

A paper that appeared on arXiv today has no ADS record yet, so it cannot come from the ADS
export. You can add its BibTeX entry to the `.bib` file by hand: instead of overwriting the file,
the action keeps any existing entry that does not overlap with the ADS export, and appends it
verbatim below a `% ----- Entries not (yet) found in ADS ... -----` comment. An entry counts as
overlapping, and is dropped, when

- an exported entry has the same key (e.g. you used the bibcode ADS later assigns), or
- an exported entry has the same arXiv identifier (`eprint`) or `doi`, and the manual key is no
  longer cited in the `.tex` file(s). If it is still cited, both are kept and a warning is logged.

On every run, each cited manual entry with an `eprint` field is also looked up on ADS by its arXiv
identifier. Once ADS has the paper, its bibcode is added to the library and (with `update_tex`
enabled) the manual key is replaced by that bibcode in the `.tex` file(s), after which the manual
entry is dropped as superseded. Manual entries are not converted by `keep_unicode`/`add_macros`.
Set `keep_manual: false` to overwrite the `.bib` file with the ADS export only.

## Setup

### 1. Link your Overleaf project to GitHub

In Overleaf: **Menu → GitHub → Sync to GitHub**.

### 2. Add your ADS API token as a repository secret

In your GitHub repository: **Settings → Secrets and variables → Actions → New repository secret**.

- Name: `ADS_TOKEN`
- Value: your ADS API token (obtainable from [ADS user settings](https://ui.adsabs.harvard.edu/user/settings/token))

### 3. Add a workflow file

Create `.github/workflows/ads-cite-sync.yml` in your repository:

```yaml
name: Sync references to ADS library

on:
  # Runs on pushes targeting the default branch
  push:
    branches: ["main"]

  # Allows you to run this workflow manually from the Actions tab
  workflow_dispatch: {}

jobs:
  update-ads-library:
    name: Update ADS references
    runs-on: ubuntu-latest

    # Needed for the action to commit the updated .bib file back
    permissions:
      contents: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v7
        with:
          ref: ${{ github.head_ref }}

      - name: Scan .tex file(s) and update ADS library
        uses: joriswitstok/ads-cite-sync@v0
        with:
          token: ${{ secrets.ADS_TOKEN }}
          library: "My ADS library"
```

## Inputs

| Input | Description | Default |
|---|---|---|
| `token` | ADS API token (**required**) | — |
| `tex_files` | Space-separated `.tex` files or glob patterns to scan | `*.tex` |
| `library` | Name of the ADS library to add bibcodes to | `Manuscript citations` |
| `description` | Description used if the library is newly created | `Bibcodes cited in a LaTeX manuscript` |
| `public` | Make a newly created library public | `false` |
| `bib_file` | Path for the exported `.bib` file | `.bib` matching a scanned `.tex` file, else the single `.bib` next to it |
| `no_bib` | Skip BibTeX export entirely | `false` |
| `keep_unicode` | Leave non-ASCII characters in the `.bib` file as-is (for LuaLaTeX/XeLaTeX) | `false` |
| `add_macros` | Expand on AASTeX macros for journal abbreviations, e.g. `\ojap` | `false` |
| `update_tex` | Replace superseded bibcodes in the scanned `.tex` file(s) | `true` |
| `keep_manual` | Preserve manually added `.bib` entries that are not (yet) on ADS | `true` |
| `commit_bib` | Commit and push the updated `.bib` file back to the repository | `true` |
| `commit_tex` | Commit and push the updated `.tex` file(s) back to the repository | `true` |
| `commit_message` | Commit message for the `.bib` and `.tex` update | `chore: update BibTeX references [skip ci]` |

## Usage notes

- **Branch name**: Overleaf's GitHub sync sometimes uses `master` rather than `main` depending
  on when the repository was created; adjust the `branches:` field in the workflow accordingly.
- **Multiple `.tex` files**: by default all `*.tex` files in the repository root are scanned.
  For a project with files in subdirectories, pass e.g. `tex_files: "*.tex sections/*.tex"`.
- **`[skip ci]`**: the default commit message includes `[skip ci]` to prevent the `.bib` commit
  from triggering another workflow run. Remove it if your setup requires otherwise.
- **Permissions**: the `contents: write` permission is required for the action to push the
  updated `.bib` and `.tex` file(s). If your repository has stricter default permissions, set this
  explicitly in the job as shown in the example above.
- **Rewritten `.tex` files**: with `update_tex` enabled (the default) the action modifies the
  LaTeX source in place. When syncing with Overleaf, pull the resulting commit into the Overleaf
  project so the two do not diverge; set `update_tex: false` (or `commit_tex: false`) to leave the
  `.tex` file(s) untouched.
- **Output `.bib` file**: unless `bib_file` is given, the export is written to the `.bib` file
  sharing its directory and stem with one of the scanned `.tex` files (e.g. `main.bib` for
  `main.tex`). If no such file exists but the directory of the first `.tex` file contains exactly
  one `.bib` file, that file is used instead; otherwise the action fails and asks for `bib_file`.
- **Unicode characters**: ADS occasionally exports raw Unicode in titles (e.g. `Lyα`, `z ≃ 9`,
  `7─14`), which makes pdfLaTeX fail with an "inputenc" error. By default these are converted to
  LaTeX macros (`{\ensuremath{\alpha}}`, `{\ensuremath{\simeq}}`, `--`, accented letters as
  `{\"{u}}`, etc.); any character without a known equivalent is left as-is with a warning in the
  log. Set `keep_unicode: true` to disable the conversion when compiling with LuaLaTeX/XeLaTeX.
- **Running the script locally**: you can also run `ads_cite_sync.py` directly:

  ```bash
  pip install requests
  python ads_cite_sync.py --token YOUR_TOKEN --tex_files main.tex sections/*.tex \
      --library "Manuscript citations" --bib_file refs.bib
  ```

  Pass `--no-update-tex` to leave superseded bibcodes in the `.tex` file(s) untouched, or
  `--no-bib` to skip the BibTeX export:

  ```bash
  python ads_cite_sync.py --token YOUR_TOKEN --no-update-tex
  ```
