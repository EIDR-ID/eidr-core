"""The eidr-core dictionary, read from the installed package.

Why this exists (operator-accepted suggestion, 2026-10-02): every project is
asked to read the dictionary before it asks eidr-core a question or proposes
a change. A copy in each project describes whatever eidr-core was when it
was published. This module answers from the dictionary that shipped WITH
the installed code, so the answer always matches what the project actually
runs, and a session can look up one name instead of reading the whole file.

    python -m eidr_core.dictionary norm_title          # one entry
    python -m eidr_core.dictionary eidr_core.normalize # one module section
    python -m eidr_core.dictionary --changes 0.44.0    # what moved since 0.44.0
    python -m eidr_core.dictionary --index             # every name, one line each

The text is ``DICTIONARY.md``, shipped as package data (``tools/
gen_dictionary.py`` keeps the package copy byte-identical to the repository
root's). Nothing here imports the rest of eidr-core, and nothing needs an
extra.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from importlib.resources import files

__all__ = ["changes", "lookup", "text"]

_MARKER = re.compile(r"<!-- dict:(?P<qual>[\w.]+) -->")
_MODULE = re.compile(r"^## `(?P<qual>eidr_core[\w.]*)`\n", re.M)


def text() -> str:
    """The whole dictionary of the installed eidr-core, as Markdown."""
    # Found through this module's package rather than by name, the same seam
    # altidtool_io uses (0.45.1). __package__, not __name__: under
    # `python -m eidr_core.dictionary` the module's __name__ is "__main__".
    pkg = __package__ or __name__.rpartition(".")[0]
    return (files(pkg) / "DICTIONARY.md").read_text(encoding="utf-8")


def _entry(doc: str, start: int) -> str:
    """From the heading that owns position ``start`` to the next heading of
    level 2 or 3."""
    head = doc.rfind("\n### ", 0, start)
    head = head + 1 if head >= 0 else start
    nxt = re.search(r"^#{2,3} ", doc[start:], re.M)
    end = start + nxt.start() if nxt else len(doc)
    return doc[head:end].rstrip() + "\n"


def lookup(name: str) -> str | None:
    """The dictionary entry for ``name``, or ``None`` when nothing matches.

    ``name`` may be bare (``norm_title``), partly qualified
    (``normalize.norm_title``) or fully qualified
    (``eidr_core.normalize.norm_title``). A module path returns that module's
    section. A bare name defined in more than one module returns every
    matching entry, separated by a rule.
    """
    doc = text()
    want = name.strip()
    if not want:
        return None
    full = want if want.startswith("eidr_core") else f"eidr_core.{want}"
    for m in _MODULE.finditer(doc):
        if m.group("qual") == full:
            nxt = _MODULE.search(doc, m.end())
            spec = doc.find("\n## Specs", m.end())
            ends = [e for e in (nxt.start() if nxt else -1, spec) if e > 0]
            return doc[m.start():min(ends) if ends else len(doc)].rstrip() + "\n"
    hits = [m for m in _MARKER.finditer(doc)
            if m.group("qual") == full or m.group("qual").endswith("." + want)]
    if not hits:
        return None
    return "\n---\n\n".join(_entry(doc, m.start()) for m in hits)


def _version_key(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def changes(since: str | None = None) -> str:
    """The Changes entries, newest first; with ``since``, only the versions
    newer than it (``changes("0.44.0")`` is everything after 0.44.0)."""
    doc = text()
    start = doc.find("\n## Changes")
    end = doc.find("\n## ", start + 1)
    section = doc[start + 1:end if end > 0 else len(doc)]
    if since is None:
        return section.rstrip() + "\n"
    floor = _version_key(since)
    parts = re.split(r"(?m)^(?=### )", section)
    keep = [p for p in parts[1:]
            if re.match(r"### \d+\.\d+\.\d+", p) and _version_key(p[4:20]) > floor]
    return "".join(keep).rstrip() + "\n" if keep else f"No changes after {since}.\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m eidr_core.dictionary",
        description="Read the eidr-core dictionary of the INSTALLED version.")
    ap.add_argument("name", nargs="?", help="a function, class, constant or module")
    ap.add_argument("--changes", nargs="?", const="", metavar="SINCE",
                    help="print the Changes entries (only those after SINCE, if given)")
    ap.add_argument("--index", action="store_true", help="print the one-line index")
    args = ap.parse_args(argv)
    # The Windows console may not be UTF-8; never fail on an em dash.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="replace")
    if args.changes is not None:
        print(changes(args.changes or None), end="")
        return 0
    if args.index:
        doc = text()
        m = re.search(r"<!-- dict-index -->\n(.*?)<!-- /dict-index -->", doc, re.S)
        print(m.group(1) if m else "", end="")
        return 0
    if not args.name:
        ap.print_help()
        return 0
    found = lookup(args.name)
    if found is None:
        print(f"{args.name}: not in the eidr-core dictionary. Try --index.", file=sys.stderr)
        return 1
    print(found, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
