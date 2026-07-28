"""
Word-alias normalisation (third-party WordAlias list + ordinals).

The list maps a submitted word to a canonical form applied token-by-token before
string-distance comparison. Two domains: CT (titles / company terms / symbols /
international name variants) and T (personal-name nicknames). Maps are made
idempotent: cycles in the source (e.g. & -> and -> &) are collapsed to a single
representative so repeated application is stable.

Symbols ('&', '+') are handled in normalize.py (-> "and") before tokenising, so
they are dropped from the token maps here.
"""
import csv
import os
import functools

_DATA = os.path.join(os.path.dirname(__file__), "data", "word_alias.csv")

# spelled ordinals -> cardinal digit (numeric ordinals like 1st/10th come from
# the CT list; roman numerals and spelled cardinals are handled in normalize)
ORDINALS = {
    "first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5",
    "sixth": "6", "seventh": "7", "eighth": "8", "ninth": "9", "tenth": "10",
    "eleventh": "11", "twelfth": "12",
}


def _resolve(raw):
    """Collapse the raw word->hash map to an idempotent canonical map."""
    canon = {}
    for w in raw:
        seen, cur = [], w
        while cur in raw and raw[cur] != cur and cur not in seen:
            seen.append(cur)
            cur = raw[cur]
        if cur in raw and raw[cur] in seen:        # cycle -> stable representative
            cur = min(seen + [cur])
        canon[w] = cur
    return canon


@functools.lru_cache(maxsize=1)
def _load():
    ct_raw, t_raw = {}, {}
    try:
        with open(_DATA, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                w, dom, h = row["word"], row.get("domain", ""), row["hash"]
                if not w or h is None:
                    continue
                if not w.isalnum() or not h.isalnum():   # drop symbol entries (&,+,b.v.)
                    continue
                (ct_raw if dom == "CT" else t_raw)[w] = h
    except FileNotFoundError:
        pass
    ct = _resolve(ct_raw)
    t = _resolve(t_raw)
    t_combined = dict(ct); t_combined.update(t)       # names get CT + T
    return ct, t_combined


def alias_title(tok):
    """Canonicalise a title/company token (ordinals + CT list)."""
    if tok in ORDINALS:
        return ORDINALS[tok]
    return _load()[0].get(tok, tok)


def alias_name(tok):
    """Canonicalise a personal/org-name token (ordinals + CT + T lists)."""
    if tok in ORDINALS:
        return ORDINALS[tok]
    return _load()[1].get(tok, tok)
