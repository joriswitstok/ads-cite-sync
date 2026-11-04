#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script for scanning a LaTeX file for ADS bibcodes, adding them to an ADS library,
optionally replacing superseded (e.g. arXiv preprint) bibcodes by their published
counterparts in the .tex file(s), and optionally exporting an up-to-date BibTeX .bib file.

Joris Witstok, 19 June 2026
"""

import os, sys, inspect
if __name__ == "__main__":
    print("Python", sys.version)

# Find current path
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))

# Import the requests package and set your token in a variable for later use
import argparse
import glob
import requests
import re
import json
import unicodedata

# Helpers for preserving manually added (non-ADS) .bib entries, shipped next to this script
sys.path.insert(0, currentdir)
import bib_merge

# Retrieve API token, LaTeX file(s), library settings, and BibTeX export options as arguments
parser = argparse.ArgumentParser()
parser.add_argument("-t", "--token", help="API token for ADS")
parser.add_argument("-f", "--tex_files", nargs="+", default=["*.tex"],
                    help="One or more .tex files or glob patterns to scan for ADS bibcodes (default: *.tex)")
parser.add_argument("-l", "--library", default="Manuscript citations", help="Name of the ADS library to add bibcodes to (created automatically if it does not exist)")
parser.add_argument("-d", "--description", default="Bibcodes cited in a LaTeX manuscript", help="Description to use if the library needs to be created")
parser.add_argument("-p", "--public", action="store_true", help="Make a newly created library public (default: private)")
parser.add_argument("-b", "--bib_file", default=None, help="Path to write the exported BibTeX .bib file to (default: the .bib file sharing its stem with a scanned .tex file, or the single .bib file in the directory of the first .tex file)")
parser.add_argument("--no-bib", action="store_true", help="Skip BibTeX export entirely")
parser.add_argument("--keep-unicode", action="store_true",
                    help="Do not convert non-ASCII characters in the exported BibTeX to LaTeX macros (e.g. when compiling with LuaLaTeX/XeLaTeX)")
parser.add_argument("-m", "--add-macros", action="store_true", help="Expand on AASTeX macros for journal abbreviations")
parser.add_argument("--no-update-tex", action="store_true",
                    help="Skip replacing superseded bibcodes (e.g. arXiv preprints that have since been published) in the scanned .tex file(s)")
parser.add_argument("--no-keep-manual", action="store_true",
                    help="Overwrite the .bib file with the ADS export only, discarding manually added entries that are not (yet) on ADS")
args = parser.parse_args()
headers = {"Authorization": "Bearer " + args.token}

def get_biblib_url(endpoint):
    return "https://api.adsabs.harvard.edu/v1/biblib/{}".format(endpoint)
 
def get_export_url(endpoint):
    return "https://api.adsabs.harvard.edu/v1/export/{}".format(endpoint)

def get_search_url(endpoint):
    return "https://api.adsabs.harvard.edu/v1/search/{}".format(endpoint)

# Regular expression matching the canonical 19-character ADS bibcode format, e.g.
# "2026OJAp....955261W": 4-digit year + 5-character (dot-padded) bibstem
# + 4-character (dot-padded) volume + 1-character qualifier + 4-character
# (dot-padded) page + 1-character first-author initial
bibcode_regex = re.compile(r"\b\d{4}[A-Za-z0-9.&]{14}[A-Za-z]\b")

# ADS BibTeX exports occasionally contain raw Unicode characters (Greek letters, math symbols,
# dashes, accented letters) which make pdfLaTeX's inputenc fail. Map the known ones to LaTeX
# macros; math symbols are wrapped in \ensuremath so they work both inside and outside math mode.
unicode_latex_map = {
    # Greek letters (lower and upper case)
    "α": r"{\ensuremath{\alpha}}", "β": r"{\ensuremath{\beta}}", "γ": r"{\ensuremath{\gamma}}",
    "δ": r"{\ensuremath{\delta}}", "ε": r"{\ensuremath{\epsilon}}", "ϵ": r"{\ensuremath{\epsilon}}",
    "ζ": r"{\ensuremath{\zeta}}", "η": r"{\ensuremath{\eta}}", "θ": r"{\ensuremath{\theta}}",
    "ι": r"{\ensuremath{\iota}}", "κ": r"{\ensuremath{\kappa}}", "λ": r"{\ensuremath{\lambda}}",
    "μ": r"{\ensuremath{\mu}}", "µ": r"{\ensuremath{\mu}}", "ν": r"{\ensuremath{\nu}}",
    "ξ": r"{\ensuremath{\xi}}", "π": r"{\ensuremath{\pi}}", "ρ": r"{\ensuremath{\rho}}",
    "σ": r"{\ensuremath{\sigma}}", "τ": r"{\ensuremath{\tau}}", "υ": r"{\ensuremath{\upsilon}}",
    "φ": r"{\ensuremath{\phi}}", "ϕ": r"{\ensuremath{\phi}}", "χ": r"{\ensuremath{\chi}}",
    "ψ": r"{\ensuremath{\psi}}", "ω": r"{\ensuremath{\omega}}",
    "Γ": r"{\ensuremath{\Gamma}}", "Δ": r"{\ensuremath{\Delta}}", "Θ": r"{\ensuremath{\Theta}}",
    "Λ": r"{\ensuremath{\Lambda}}", "Ξ": r"{\ensuremath{\Xi}}", "Π": r"{\ensuremath{\Pi}}",
    "Σ": r"{\ensuremath{\Sigma}}", "Φ": r"{\ensuremath{\Phi}}", "Ψ": r"{\ensuremath{\Psi}}",
    "Ω": r"{\ensuremath{\Omega}}",
    # Math and comparison symbols
    "≃": r"{\ensuremath{\simeq}}", "≈": r"{\ensuremath{\approx}}", "∼": r"{\ensuremath{\sim}}",
    "≤": r"{\ensuremath{\leq}}", "≥": r"{\ensuremath{\geq}}", "≲": r"{\ensuremath{\lesssim}}",
    "≳": r"{\ensuremath{\gtrsim}}", "≠": r"{\ensuremath{\neq}}", "≡": r"{\ensuremath{\equiv}}",
    "∝": r"{\ensuremath{\propto}}", "∞": r"{\ensuremath{\infty}}", "×": r"{\ensuremath{\times}}",
    "±": r"{\ensuremath{\pm}}", "∓": r"{\ensuremath{\mp}}", "−": r"{\ensuremath{-}}",
    "→": r"{\ensuremath{\rightarrow}}", "←": r"{\ensuremath{\leftarrow}}", "√": r"{\ensuremath{\surd}}",
    "∑": r"{\ensuremath{\sum}}", "∫": r"{\ensuremath{\int}}", "∂": r"{\ensuremath{\partial}}",
    "∇": r"{\ensuremath{\nabla}}", "⊙": r"{\ensuremath{\odot}}", "☉": r"{\ensuremath{\odot}}",
    "°": r"{\ensuremath{^\circ}}", "′": r"{\ensuremath{^\prime}}", "″": r"{\ensuremath{^{\prime\prime}}}",
    "¹": r"{\ensuremath{^1}}", "²": r"{\ensuremath{^2}}", "³": r"{\ensuremath{^3}}",
    "⁻": r"{\ensuremath{^-}}", "⁺": r"{\ensuremath{^+}}",
    "Å": r"{\AA}", "å": r"{\aa}",
    # Dashes, spaces, quotes and other punctuation
    "–": "--", "—": "---", "―": "---", "─": "--", "‐": "-", "‑": "-", "‒": "--",
    " ": "~", " ": r"\,", " ": r"\,", " ": r"\ ", " ": r"\ ",
    "‘": "`", "’": "'", "‚": ",", "“": "``", "”": "''", "„": ",,",
    "…": r"\dots", "•": r"\textbullet", "·": r"{\ensuremath{\cdot}}", "†": r"\dag", "‡": r"\ddag",
    "§": r"\S", "¶": r"\P", "©": r"\copyright", "®": r"\textregistered", "™": r"\texttrademark",
    "€": r"\euro", "£": r"\pounds", "‰": r"\textperthousand", "¿": r"?`", "¡": r"!`",
    # Letters without a combining-accent decomposition
    "ß": r"{\ss}", "æ": r"{\ae}", "Æ": r"{\AE}", "œ": r"{\oe}", "Œ": r"{\OE}",
    "ø": r"{\o}", "Ø": r"{\O}", "ł": r"{\l}", "Ł": r"{\L}", "đ": r"{\dj}", "Đ": r"{\DJ}",
    "ð": r"{\dh}", "Ð": r"{\DH}", "þ": r"{\th}", "Þ": r"{\TH}", "ı": r"{\i}", "ȷ": r"{\j}",
}

# Combining diacritical marks (from NFD decomposition) mapped to LaTeX accent commands
combining_accent_map = {
    "̀": "`", "́": "'", "̂": "^", "̃": "~", "̈": '"', "̄": "=",
    "̆": "u", "̇": ".", "̊": "r", "̋": "H", "̌": "v", "̧": "c",
    "̨": "k", "̣": "d", "̱": "b",
}

def unicode_to_latex(text):
    """Replace non-ASCII characters in a string by equivalent LaTeX macros where possible.
    Returns the converted text and a sorted list of characters that could not be converted."""
    out = []
    unconverted = set()
    for char in text:
        if ord(char) < 128:
            out.append(char)
        elif char in unicode_latex_map:
            out.append(unicode_latex_map[char])
        else:
            # Try decomposing accented letters into base letter + combining accent(s)
            decomposed = unicodedata.normalize("NFD", char)
            base, accents = decomposed[0], decomposed[1:]
            if ord(base) < 128 and accents and all(a in combining_accent_map for a in accents):
                latex = base
                # Dotless i/j are needed for accents placed above the letter
                for a in accents:
                    cmd = combining_accent_map[a]
                    if latex in ("i", "j") and cmd not in ("c", "k", "d", "b"):
                        latex = "\\" + latex
                    latex = "{\\" + cmd + "{" + latex + "}}"
                out.append(latex)
            else:
                out.append(char)
                unconverted.add(char)
    return "".join(out), sorted(unconverted)

# Resolve all glob patterns and collect matched .tex files, preserving order and deduplicating
tex_files = list(dict.fromkeys(f for pattern in args.tex_files for f in sorted(glob.glob(pattern))))
if not tex_files:
    sys.exit("No .tex files matched the pattern(s): {}".format(', '.join(args.tex_files)))
print("Scanning {:d} .tex file(s): {}".format(len(tex_files), ', '.join(tex_files)))

# Determine the output .bib path up front, since its current contents (manually added entries)
# are needed before the .tex file(s) are updated: default to the .bib file sharing its directory
# and stem with one of the scanned .tex files; failing that, fall back to a single existing .bib
# file in the directory of the first .tex file
bib_path = None
existing_bib = ""
if not args.no_bib:
    if args.bib_file:
        bib_path = args.bib_file
    else:
        for tex_file in tex_files:
            candidate = os.path.splitext(tex_file)[0] + ".bib"
            if os.path.isfile(candidate):
                bib_path = candidate
                break
        if bib_path is None:
            tex_dir = os.path.dirname(tex_files[0]) or "."
            bib_candidates = sorted(glob.glob(os.path.join(tex_dir, "*.bib")))
            if len(bib_candidates) == 1:
                bib_path = bib_candidates[0]
                print("No .bib file matching a scanned .tex file found, falling back to {}".format(bib_path))
            elif len(bib_candidates) == 0:
                sys.exit("No .bib file found in {}; specify the output path with --bib_file".format(tex_dir))
            else:
                sys.exit("No .bib file matching a scanned .tex file found and multiple candidates exist in {} ({}); "
                         "specify the output path with --bib_file".format(tex_dir, ", ".join(bib_candidates)))
    if not args.no_keep_manual and os.path.isfile(bib_path):
        with open(bib_path, 'r', encoding="utf-8") as f:
            existing_bib = f.read()

def read_tex():
    """Return the concatenated contents of all scanned .tex files."""
    texts = []
    for tex_file in tex_files:
        with open(tex_file, 'r', encoding="utf-8") as f:
            texts.append(f.read())
    return "\n".join(texts)

# Read and concatenate all matched .tex files, then scan the combined text for bibcodes
bibcodes_per_file = {}
for tex_file in tex_files:
    with open(tex_file, 'r', encoding="utf-8") as f:
        bibcodes_per_file[tex_file] = bibcode_regex.findall(f.read())
    print("  {:s}: {:d} bibcode(s) found".format(tex_file, len(bibcodes_per_file[tex_file])))

# Merge into a single deduplicated list, preserving first-appearance order across files
bibcodes = list(dict.fromkeys(b for matches in bibcodes_per_file.values() for b in matches))
n_bibcodes = len(bibcodes)
print("Found {:d} unique ADS bibcode(s) across all scanned files".format(n_bibcodes))
if n_bibcodes == 0:
    sys.exit("No bibcodes found, exiting.")

# Retrieve all libraries belonging to the user and look for one matching the requested name
libraries = requests.get(get_biblib_url("libraries"), headers=headers).json()["libraries"]
matches = [lib for lib in libraries if lib["name"] == args.library]

if matches:
    library_id = matches[0]["id"]
    print("Found existing library '{}' ({:d} documents)".format(args.library, matches[0]["num_documents"]))
else:
    # Create the library if it does not exist yet
    headers["Content-type"] = "application/json"
    payload = {"name": args.library, "description": args.description, "public": args.public}
    library = requests.post(get_biblib_url("libraries"), headers=headers, data=json.dumps(payload)).json()
    library_id = library["id"]
    print("Created new library '{}' (ID {})".format(args.library, library_id))

# Add the bibcodes found in the LaTeX file to the library
headers["Content-type"] = "application/json"

# Add bibcodes to the library in chunks of 100
chunk_size = 100  # maximum allowed per request

def add_to_library(bibcodes_to_add):
    """Add bibcodes to the library; returns the number added and the list of invalid bibcodes."""
    n_added = 0
    invalid = []
    for i in range(0, len(bibcodes_to_add), chunk_size):
        chunk = bibcodes_to_add[i:i + chunk_size]
        result = requests.post(
            get_biblib_url("documents/" + library_id),
            headers=headers,
            data=json.dumps({"bibcode": chunk, "action": "add"})
        ).json()
        n_added += result.get("number_added", 0)
        invalid.extend(result.get("invalid_bibcodes", []))
    return n_added, invalid

n_added, invalid_bibcodes = add_to_library(bibcodes)

print("Added {:d} bibcodes to library '{}'".format(n_added, args.library))
if invalid_bibcodes:
    print("The following {:d} bibcodes were not recognised by ADS and were not added:".format(len(invalid_bibcodes)))
    for bibcode in invalid_bibcodes:
        print("  {}".format(bibcode))

# Fetch all bibcodes currently in the library (paginated); needed both to detect superseded
# bibcodes in the .tex file(s) and to export the BibTeX entries
library_bibcodes = []
if not (args.no_bib and args.no_update_tex):
    start = 0
    while True:
        response = requests.get(
            get_biblib_url("libraries/{}".format(library_id)),
            headers=headers,
            params={"start": start, "rows": chunk_size}
        ).json()
        library_bibcodes.extend(response["documents"])
        start += chunk_size
        if start >= response["metadata"]["num_documents"]:
            break

# Replace superseded bibcodes in the .tex file(s) unless explicitly skipped: ADS merges an
# arXiv preprint record (e.g. 2025arXiv250918302P) into the published record (2026A&A...712A.113P)
# once it appears, keeping the preprint bibcode only as an alternate. The library therefore holds
# the canonical, published bibcode, while the .tex file(s) may still cite the superseded one
if not args.no_update_tex:
    library_bibcode_set = set(library_bibcodes)

    # Any cited bibcode absent from the library was either not recognised by ADS
    # or has been superseded by (merged into) another, canonical bibcode
    candidates = [b for b in bibcodes if b not in library_bibcode_set]
    replacements = {}

    if candidates:
        print("Checking {:d} cited bibcode(s) absent from library '{}' for superseded records...".format(
                len(candidates), args.library))
        candidate_set = set(candidates)

        # Resolve the canonical bibcode of each candidate: searching on "identifier" also
        # matches alternate (superseded) bibcodes, while "bibcode" in the response is canonical
        search_chunk_size = 50
        for i in range(0, len(candidates), search_chunk_size):
            chunk = candidates[i:i + search_chunk_size]
            search_response = requests.get(
                get_search_url("query"),
                headers=headers,
                params={"q": "identifier:({})".format(' OR '.join('"{}"'.format(b) for b in chunk)),
                        "fl": "bibcode,alternate_bibcode", "rows": len(chunk)}
            )
            search_response.raise_for_status()
            for doc in search_response.json()["response"]["docs"]:
                canonical = doc["bibcode"]
                for alternate in doc.get("alternate_bibcode", []):
                    if alternate in candidate_set and alternate != canonical:
                        replacements[alternate] = canonical

    # Manually added .bib entries (e.g. a preprint that was not yet on ADS when it was cited)
    # may since have received an ADS record, possibly under a different bibcode than their key:
    # look up each cited manual entry with an arXiv identifier and, if found, cite the ADS record
    if existing_bib:
        tex_text = read_tex()
        manual_eprints = {}
        for block in bib_merge.parse_bib(existing_bib):
            key = block["key"]
            if key is None or key in library_bibcode_set or key in replacements:
                continue
            eprint = bib_merge.normalise_eprint(bib_merge.get_field(block["raw"], "eprint"))
            if eprint and bib_merge.is_cited(key, tex_text):
                manual_eprints[eprint] = key

        if manual_eprints:
            print("Checking {:d} cited manual .bib entr{} for new ADS records...".format(
                    len(manual_eprints), "y" if len(manual_eprints) == 1 else "ies"))
            eprints = list(manual_eprints)
            search_chunk_size = 50
            for i in range(0, len(eprints), search_chunk_size):
                chunk = eprints[i:i + search_chunk_size]
                search_response = requests.get(
                    get_search_url("query"),
                    headers=headers,
                    params={"q": "identifier:({})".format(' OR '.join('"arXiv:{}"'.format(e) for e in chunk)),
                            "fl": "bibcode,identifier", "rows": len(chunk)}
                )
                search_response.raise_for_status()
                for doc in search_response.json()["response"]["docs"]:
                    for identifier in doc.get("identifier", []):
                        eprint = bib_merge.normalise_eprint(identifier)
                        if eprint in manual_eprints:
                            key = manual_eprints[eprint]
                            if doc["bibcode"] != key:
                                replacements[key] = doc["bibcode"]
                            break

            # Add the newly found ADS records to the library so that they are exported below
            new_bibcodes = list(dict.fromkeys(b for b in replacements.values() if b not in library_bibcode_set))
            if new_bibcodes:
                n_new, _ = add_to_library(new_bibcodes)
                print("Added {:d} ADS record(s) of manual .bib entries to library '{}'".format(n_new, args.library))
                library_bibcodes.extend(new_bibcodes)
                library_bibcode_set.update(new_bibcodes)

    if replacements:
        print("Found {:d} superseded bibcode(s):".format(len(replacements)))
        for old_bibcode, new_bibcode in replacements.items():
            print("  {} -> {}".format(old_bibcode, new_bibcode))

        # Replace all whole-word occurrences in each .tex file containing them
        # (keys of manual entries need not be bibcodes, so match on BibTeX key characters
        # rather than on word boundaries)
        superseded_regex = re.compile(r"(?<![{0}])(?:{1})(?![{0}])".format(
                bib_merge.KEY_CHARS, '|'.join(re.escape(b) for b in replacements)))
        for tex_file in tex_files:
            with open(tex_file, 'r', encoding="utf-8") as f:
                text = f.read()
            text, n_replaced = superseded_regex.subn(lambda m: replacements[m.group(0)], text)
            if n_replaced:
                with open(tex_file, 'w', encoding="utf-8") as f:
                    f.write(text)
                print("  Updated {:d} bibcode instance(s) in {}".format(n_replaced, tex_file))

        # Keep the in-memory list consistent with the updated .tex file(s)
        bibcodes = list(dict.fromkeys(replacements.get(b, b) for b in bibcodes))
    else:
        print("No superseded bibcodes found in the scanned .tex file(s)")

# Export a BibTeX .bib file for all valid bibcodes unless explicitly skipped
if not args.no_bib:
    print("Fetching BibTeX entries for {:d} bibcodes in library '{}'...".format(
            len(library_bibcodes), args.library))

    # Export bibcodes into bibtex file
    bibtex_chunks = []
    for i in range(0, len(library_bibcodes), chunk_size):
        chunk = library_bibcodes[i:i + chunk_size]
        export_response = requests.post(
            get_export_url("bibtex"),
            headers=headers,
            data=json.dumps({"bibcode": chunk})
        )
        export_response.raise_for_status()
        bibtex_chunks.append(export_response.json()["export"])
    bibtex = "\n".join(bibtex_chunks)

    if args.add_macros:
        journal_replacements = {
            r"The Open Journal of Astrophysics": r"\ojap",
            r"Nature Astronomy": r"\natas",
            r"Reviews of Modern Physics": r"\revmodphys",
        }

        # Replace occurrences with regex
        for pattern, replacement in journal_replacements.items():
            bibtex = re.sub(
                r"(journal\s*=\s*\{)" + pattern + r"(\})",
                lambda m, r=replacement: m.group(1) + r + m.group(2),
                bibtex
            )

    if not args.keep_unicode:
        # Convert raw Unicode characters in the export to LaTeX macros so that pdfLaTeX can
        # compile the .bib file (ADS exports e.g. "Lyα" or "z ≃ 9" verbatim)
        n_nonascii = sum(1 for c in bibtex if ord(c) >= 128)
        bibtex, unconverted = unicode_to_latex(bibtex)
        if n_nonascii:
            print("Converted {:d} non-ASCII character(s) in the BibTeX export to LaTeX macros".format(
                    n_nonascii - sum(bibtex.count(c) for c in unconverted)))
        if unconverted:
            print("Warning: no LaTeX equivalent known for the following character(s), left as-is: {}".format(
                    ", ".join("'{}' (U+{:04X})".format(c, ord(c)) for c in unconverted)))

    # Preserve manually added entries from the existing .bib file (e.g. preprints not yet on
    # ADS), unless they overlap with the ADS export; they are appended verbatim (no Unicode
    # conversion or macro expansion) below a header comment
    kept = []
    if existing_bib:
        print("Checking existing {} for manually added entries...".format(bib_path))
        kept = bib_merge.manual_blocks(existing_bib, bibtex, read_tex())
        bibtex = bib_merge.merge(bibtex, kept)
        if kept:
            print("Preserved {:d} manually added block(s) not found in ADS:".format(len(kept)))
            for block in kept:
                print("  {}".format(block["key"] or "@" + block["type"]))

    with open(bib_path, 'w', encoding="utf-8") as f:
        f.write(bibtex)
    print("Wrote BibTeX for {:d} ADS entries{} to {}".format(
            len(library_bibcodes), " and {:d} manual block(s)".format(len(kept)) if kept else "", bib_path))