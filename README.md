# ADS references synchronisation

A GitHub Action that scans LaTeX file(s) for [ADS](https://ui.adsabs.harvard.edu/) bibcodes,
adds them to an ADS library, and exports an up-to-date BibTeX `.bib` file — designed to run
automatically whenever an [Overleaf](https://www.overleaf.com/) project is synced to GitHub.

## How it works

The script scans `.tex` file(s) for strings matching the canonical 19-character ADS bibcode
format (e.g. `2026OJAp....955261W`). It then:

1. Adds all found bibcodes to a named ADS library (creating it if it does not exist).
2. Fetches up-to-date BibTeX entries for all valid bibcodes from ADS.
3. Writes a `.bib` file and, optionally, commits it back to the repository.

Because it scans for raw bibcodes rather than parsing citation commands, it works with any
LaTeX citation style, as long as bibcodes are used as BibTeX keys (the default when exporting
from ADS).

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
name: Sync citations to ADS library

on:
  push:
    branches: [main]
  workflow_dispatch: {}

jobs:
  update-ads-library:
    runs-on: ubuntu-latest
    # Needed for the action to commit the updated .bib file back
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - uses: joriswitstok/ads-cite-sync@v1
        with:
          token: ${{ secrets.ADS_TOKEN }}
          library: "Manuscript citations"
```

## Inputs

| Input | Description | Default |
|---|---|---|
| `token` | ADS API token (**required**) | — |
| `tex_files` | Space-separated `.tex` files or glob patterns to scan | `*.tex` |
| `library` | Name of the ADS library to add bibcodes to | `Manuscript citations` |
| `description` | Description used if the library is newly created | `Bibcodes cited in a LaTeX manuscript` |
| `public` | Make a newly created library public | `false` |
| `bib_file` | Path for the exported `.bib` file | `refs.bib` next to first `.tex` file |
| `no_bib` | Skip BibTeX export entirely | `false` |
| `commit_bib` | Commit and push the updated `.bib` file back to the repository | `true` |
| `commit_message` | Commit message for the `.bib` update | `chore: update BibTeX references [skip ci]` |

## Usage notes

- **Branch name**: Overleaf's GitHub sync sometimes uses `master` rather than `main` depending
  on when the repository was created; adjust the `branches:` field in the workflow accordingly.
- **Multiple `.tex` files**: by default all `*.tex` files in the repository root are scanned.
  For a project with files in subdirectories, pass e.g. `tex_files: "*.tex sections/*.tex"`.
- **`[skip ci]`**: the default commit message includes `[skip ci]` to prevent the `.bib` commit
  from triggering another workflow run. Remove it if your setup requires otherwise.
- **Permissions**: the `contents: write` permission is required for the action to push the
  updated `.bib` file. If your repository has stricter default permissions, set this explicitly
  in the job as shown in the example above.
- **Running the script locally**: you can also run `ads_cite_sync.py` directly:

  ```bash
  pip install requests
  python ads_cite_sync.py --token YOUR_TOKEN --tex_files main.tex sections/*.tex \
      --library "Manuscript citations" --bib_file refs.bib
  ```