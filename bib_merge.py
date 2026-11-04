# -*- coding: utf-8 -*-
"""
Helpers for preserving manually added (non-ADS) entries in a BibTeX file that is otherwise
regenerated from an ADS export, e.g. a preprint that appeared on arXiv today and has no ADS
record yet.

A manual entry is kept unless it overlaps with the ADS export, i.e. it shares its key, or it
shares an arXiv identifier or DOI with an exported entry while its key is no longer cited.

Joris Witstok, 4 November 2026
"""

import re

# Header written above the preserved entries; BibTeX ignores text outside @-blocks, so this is a
# plain comment line. It is not parsed as an entry and is regenerated on every run
MANUAL_HEADER = "% ----- Entries not (yet) found in ADS, preserved by ads-cite-sync -----"

# Characters that may occur in a BibTeX key (ADS bibcodes use letters, digits, "." and "&")
KEY_CHARS = r"\w.&:/+\-"

def parse_bib(text):
    """Split BibTeX text into a list of blocks in their original order.

    Each block is a dict with "type" (lower case, e.g. "article", "misc", "string"), "key"
    (None for @string/@preamble/@comment) and "raw" (the verbatim text of the block).
    Text outside @-blocks (comments, blank lines) is discarded.
    """
    blocks = []
    pos = 0
    entry_start = re.compile(r"@\s*([A-Za-z]+)\s*([{(])")
    while True:
        m = entry_start.search(text, pos)
        if m is None:
            break
        open_char = m.group(2)
        close_char = "}" if open_char == "{" else ")"
        # Find the matching closing delimiter, counting nested delimiters of the same kind
        depth = 0
        end = None
        for i in range(m.end() - 1, len(text)):
            c = text[i]
            if c == open_char:
                depth += 1
            elif c == close_char:
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            # Unbalanced block: keep the remainder verbatim rather than silently losing it
            end = len(text)
        raw = text[m.start():end]
        entry_type = m.group(1).lower()
        key = None
        if entry_type not in ("string", "preamble", "comment"):
            key_match = re.match(r"\s*([^,\s]+)\s*,", text[m.end():end])
            if key_match:
                key = key_match.group(1)
        blocks.append({"type": entry_type, "key": key, "raw": raw.strip()})
        pos = end
    return blocks

def get_field(raw, field):
    """Return the value of a field in a raw BibTeX entry (braces/quotes stripped), or None."""
    m = re.search(r"(?:^|[,\s{])" + field + r"\s*=\s*", raw, flags=re.IGNORECASE)
    if m is None:
        return None
    rest = raw[m.end():]
    if rest.startswith("{"):
        depth = 0
        for i, c in enumerate(rest):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return rest[1:i].strip()
        return None
    if rest.startswith('"'):
        end = rest.find('"', 1)
        return rest[1:end].strip() if end > 0 else None
    bare = re.match(r"[^,\s}]+", rest)
    return bare.group(0) if bare else None

def normalise_eprint(value):
    """Normalise an arXiv identifier, e.g. "arXiv:2611.05349v2" -> "2611.05349"."""
    if not value:
        return None
    value = value.strip().lower()
    value = re.sub(r"^(?:https?://arxiv\.org/abs/|arxiv:)", "", value)
    value = re.sub(r"v\d+$", "", value)
    return value or None

def normalise_doi(value):
    """Normalise a DOI, e.g. "https://doi.org/10.1093/X" -> "10.1093/x"."""
    if not value:
        return None
    value = value.strip().lower()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", value)
    return value or None

def identifiers(raw):
    """Return the set of normalised identifiers ("arxiv:<id>", "doi:<doi>") of a raw entry."""
    ids = set()
    eprint = normalise_eprint(get_field(raw, "eprint"))
    if eprint:
        ids.add("arxiv:" + eprint)
    doi = normalise_doi(get_field(raw, "doi"))
    if doi:
        ids.add("doi:" + doi)
    return ids

def is_cited(key, tex_text):
    """Whether a BibTeX key occurs as a whole word in the (concatenated) LaTeX source."""
    pattern = r"(?<![{0}]){1}(?![{0}])".format(KEY_CHARS, re.escape(key))
    return re.search(pattern, tex_text) is not None

def manual_blocks(existing_text, export_text, tex_text, verbose=True):
    """Select the blocks from an existing .bib file that should survive a fresh ADS export.

    An @-block from the existing file is kept unless:
    - it is an entry whose key also occurs in the ADS export (case-insensitive, as in BibTeX), or
    - it shares an arXiv identifier or DOI with an exported entry and its key is no longer cited
      in the LaTeX source (i.e. it has been superseded by the ADS record).
    @string/@preamble/@comment blocks are kept unless an identical block is in the export.
    Returns the list of kept blocks, in their original order.
    """
    export_blocks = parse_bib(export_text)
    export_keys = {b["key"].lower() for b in export_blocks if b["key"]}
    export_raws = {b["raw"] for b in export_blocks}
    export_ids = {}
    for b in export_blocks:
        if b["key"]:
            for identifier in identifiers(b["raw"]):
                export_ids.setdefault(identifier, b["key"])

    kept = []
    seen_keys = set()
    for b in parse_bib(existing_text):
        if b["key"] is None:
            if b["raw"] not in export_raws:
                kept.append(b)
            continue
        key_lower = b["key"].lower()
        if key_lower in export_keys or key_lower in seen_keys:
            continue
        overlap = sorted(export_ids[i] for i in identifiers(b["raw"]) if i in export_ids)
        cited = is_cited(b["key"], tex_text)
        if overlap and not cited:
            if verbose:
                print("  Dropping manual entry {} (superseded by ADS entry {})".format(b["key"], overlap[0]))
            continue
        if overlap and verbose:
            print("  Warning: manual entry {} duplicates ADS entry {} but is still cited; "
                  "keeping both".format(b["key"], overlap[0]))
        kept.append(b)
        seen_keys.add(key_lower)
    return kept

def merge(export_text, kept_blocks):
    """Append the kept manual blocks to the ADS export under a header comment."""
    if not kept_blocks:
        return export_text
    return "{}\n\n{}\n\n{}\n".format(export_text.rstrip("\n"), MANUAL_HEADER,
                                     "\n\n".join(b["raw"] for b in kept_blocks))
