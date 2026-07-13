#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script for scanning a LaTeX file for ADS bibcodes, adding them to an ADS library,
and optionally exporting an up-to-date BibTeX .bib file.

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

# Retrieve API token, LaTeX file(s), library settings, and BibTeX export options as arguments
parser = argparse.ArgumentParser()
parser.add_argument("-t", "--token", help="API token for ADS")
parser.add_argument("-f", "--tex_files", nargs="+", default=["*.tex"],
                    help="One or more .tex files or glob patterns to scan for ADS bibcodes (default: *.tex)")
parser.add_argument("-l", "--library", default="Manuscript citations", help="Name of the ADS library to add bibcodes to (created automatically if it does not exist)")
parser.add_argument("-d", "--description", default="Bibcodes cited in a LaTeX manuscript", help="Description to use if the library needs to be created")
parser.add_argument("-p", "--public", action="store_true", help="Make a newly created library public (default: private)")
parser.add_argument("-b", "--bib_file", default=None, help="Path to write the exported BibTeX .bib file to (default: refs.bib in the directory of the first matched .tex file)")
parser.add_argument("--no_bib", action="store_true", help="Skip BibTeX export entirely")
args = parser.parse_args()
headers = {"Authorization": "Bearer " + args.token}

def get_biblib_url(endpoint):
    return "https://api.adsabs.harvard.edu/v1/biblib/{}".format(endpoint)
 
def get_export_url(endpoint):
    return "https://api.adsabs.harvard.edu/v1/export/{}".format(endpoint)

# Regular expression matching the canonical 19-character ADS bibcode format, e.g.
# "2026OJAp....955261W": 4-digit year + 5-character (dot-padded) bibstem
# + 4-character (dot-padded) volume + 1-character qualifier + 4-character
# (dot-padded) page + 1-character first-author initial
bibcode_regex = re.compile(r"\b\d{4}[A-Za-z0-9.&]{14}[A-Za-z]\b")

# Resolve all glob patterns and collect matched .tex files, preserving order and deduplicating
tex_files = list(dict.fromkeys(f for pattern in args.tex_files for f in sorted(glob.glob(pattern))))
if not tex_files:
    sys.exit("No .tex files matched the pattern(s): {}".format(', '.join(args.tex_files)))
print("Scanning {:d} .tex file(s): {}".format(len(tex_files), ', '.join(tex_files)))

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
payload = {"bibcode": bibcodes, "action": "add"}
results = requests.post(get_biblib_url("documents/" + library_id), headers=headers, data=json.dumps(payload)).json()

n_added = results.get("number_added", 0)
invalid_bibcodes = results.get("invalid_bibcodes", [])
print("Added {:d} bibcodes to library '{}'".format(n_added, args.library))
if invalid_bibcodes:
    print("The following {:d} bibcodes were not recognised by ADS and were not added:".format(len(invalid_bibcodes)))
    for bibcode in invalid_bibcodes:
        print("  {}".format(bibcode))

# Export a BibTeX .bib file for all valid bibcodes unless explicitly skipped
if not args.no_bib:
    valid_bibcodes = [b for b in bibcodes if b not in invalid_bibcodes]
    print("Fetching BibTeX entries for {:d} bibcodes...".format(len(valid_bibcodes)))
 
    headers["Content-type"] = "application/json"
    export_response = requests.post(get_export_url("bibtex"),
                                    headers=headers,
                                    data=json.dumps({"bibcode": valid_bibcodes}))
    export_response.raise_for_status()
    bibtex = export_response.json()["export"]
 
    # Determine output path: default to same directory and stem as the (first matching) .tex file
    if args.bib_file:
        bib_path = args.bib_file
    else:
        for ti, tex_file in enumerate(tex_files):
            tex_stem = os.path.splitext(tex_file)[0]
            bib_path = tex_stem + ".bib"
            if os.path.isfile(bib_path):
                break
            elif ti == len(tex_files) - 1:
                raise ValueError("no matching .bib file found")
 
    with open(bib_path, 'w', encoding="utf-8") as f:
        f.write(bibtex)
    print("Wrote BibTeX for {:d} entries to {}".format(len(valid_bibcodes), bib_path))