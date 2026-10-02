"""Generate and check DICTIONARY.md, the eidr-core dictionary.

Why this exists (operator, 2026-10-02): every consumer must be able to find
what eidr-core already does BEFORE it writes its own version or proposes a
new one. A consumer that cannot find the shared function writes a second
one, and the portfolio's rule is that a second implementation is a bug
until proven otherwise (CLAUDE.md, "The organizing rule").

How it stays true. The dictionary has two halves:

* **Generated blocks**, written by this tool from the source: each public
  symbol's exact signature, its parameters with their types and defaults,
  and its return type. They cannot drift, because ``--check`` regenerates
  them and fails on any difference.
* **Authored prose** around and inside them: what a symbol does, each
  parameter's purpose, and when to use the module or not. The tool keeps
  every purpose cell across regenerations, keyed by parameter name. It
  fails when a cell is empty or ``TODO``, when a public symbol has no
  entry, when an entry names a symbol that no longer exists, or when the
  ``Changes`` section has no heading for the version in ``pyproject.toml``.
  So a release cannot ship without its dictionary update.

``tests/test_dictionary.py`` runs the check in the suite, so CI enforces it
at both ends of the supported Python range. Annotations and defaults are
taken as SOURCE TEXT (``ast.get_source_segment``), not ``ast.unparse``, so
the output is identical on every Python version.

What counts as public: a module's ``__all__`` when it has one. Otherwise,
its top-level functions, classes and UPPER_CASE constants without a leading
underscore, plus the explicit re-exports in ``EXTRA_PUBLIC``. Modules whose
own name starts with ``_`` are private and skipped. A name in a package's
``__all__`` that is imported from a submodule is documented once, under the
package path the consumer imports it from.

Usage:
    python tools/gen_dictionary.py --check   # exit 1 and list every problem
    python tools/gen_dictionary.py --write   # refresh blocks, add skeletons
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "eidr_core"
DICT = ROOT / "DICTIONARY.md"

# Re-exports that a module without __all__ makes public on purpose. Keep
# this short. The better fix is an __all__ in the module, which makes the
# public surface explicit for everyone, not only for this tool.
EXTRA_PUBLIC: dict[str, list[str]] = {
    "eidr_core.compare": ["set_params"],
}

TODO = "TODO"
VALUE_MAX = 90  # longer constant values are shown truncated

BLOCK_RE = re.compile(
    r"<!-- dict:(?P<qual>[\w.]+) -->\n(?P<body>.*?)<!-- /dict -->", re.S)
MODULE_RE = re.compile(
    r"<!-- dict-module:(?P<qual>[\w.]+) -->\n(?P<body>.*?)<!-- /dict-module -->", re.S)
INDEX_RE = re.compile(r"<!-- dict-index -->\n(?P<body>.*?)<!-- /dict-index -->", re.S)
VERSION_RE = re.compile(r"<!-- dict-version -->(?P<body>.*?)<!-- /dict-version -->", re.S)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

@dataclass
class Param:
    name: str
    annotation: str
    default: str | None
    kind: str  # "pos-only", "normal", "var-positional", "kw-only", "var-keyword"


@dataclass
class Symbol:
    qual: str            # the path a consumer imports it from
    module: str          # that module
    name: str
    kind: str            # "function", "class", "constant"
    defined_in: str      # source file, relative to the repo root
    line: int
    params: list[Param] = field(default_factory=list)
    returns: str = ""
    is_async: bool = False
    decorators: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    fields: list[Param] = field(default_factory=list)       # class fields
    methods: list[Symbol] = field(default_factory=list)     # class methods
    value: str = ""                                         # constant value
    annotation: str = ""                                    # constant annotation


@dataclass
class Module:
    qual: str
    path: Path
    tree: ast.Module
    source: str
    all_names: list[str] | None
    imports: dict[str, tuple[str, str]]  # local name -> (module, name)


def _module_qual(path: Path) -> str:
    rel = path.relative_to(SRC.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_private_module(qual: str) -> bool:
    return any(p.startswith("_") for p in qual.split(".")[1:])


def _resolve_relative(mod: Module, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    base = mod.qual.split(".")
    if mod.path.name != "__init__.py":
        base = base[:-1]
    base = base[: len(base) - (node.level - 1)]
    return ".".join(base + ([node.module] if node.module else []))


def load_modules() -> dict[str, Module]:
    mods: dict[str, Module] = {}
    for path in sorted(SRC.rglob("*.py")):
        qual = _module_qual(path)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        mod = Module(qual, path, tree, source, None, {})
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
                mod.all_names = list(ast.literal_eval(node.value))
            elif isinstance(node, ast.ImportFrom):
                src_mod = _resolve_relative(mod, node)
                for a in node.names:
                    mod.imports[a.asname or a.name] = (src_mod, a.name)
        mods[qual] = mod
    return mods


def _seg(mod: Module, node: ast.AST | None) -> str:
    if node is None:
        return ""
    text = ast.get_source_segment(mod.source, node) or ""
    return " ".join(text.split())  # one line, whatever the source wrapping


def _params(mod: Module, args: ast.arguments, drop_first: bool) -> list[Param]:
    out: list[Param] = []
    positional = list(args.posonlyargs) + list(args.args)
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    for i, (a, d) in enumerate(zip(positional, defaults, strict=True)):
        kind = "pos-only" if i < len(args.posonlyargs) else "normal"
        out.append(Param(a.arg, _seg(mod, a.annotation), _seg(mod, d) if d else None, kind))
    if args.vararg:
        out.append(Param("*" + args.vararg.arg, _seg(mod, args.vararg.annotation), None,
                         "var-positional"))
    for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        out.append(Param(a.arg, _seg(mod, a.annotation), _seg(mod, d) if d else None, "kw-only"))
    if args.kwarg:
        out.append(Param("**" + args.kwarg.arg, _seg(mod, args.kwarg.annotation), None,
                         "var-keyword"))
    if drop_first and out and out[0].name in ("self", "cls"):
        out = out[1:]
    return out


def _function(mod: Module, node: ast.FunctionDef | ast.AsyncFunctionDef, qual: str,
              in_class: bool = False) -> Symbol:
    decos = [_seg(mod, d) for d in node.decorator_list]
    is_static = "staticmethod" in decos
    return Symbol(
        qual=qual, module=mod.qual, name=node.name, kind="function",
        defined_in=str(mod.path.relative_to(ROOT)).replace("\\", "/"), line=node.lineno,
        params=_params(mod, node.args, drop_first=in_class and not is_static),
        returns=_seg(mod, node.returns), is_async=isinstance(node, ast.AsyncFunctionDef),
        decorators=decos)


def _class(mod: Module, node: ast.ClassDef, qual: str) -> Symbol:
    sym = Symbol(
        qual=qual, module=mod.qual, name=node.name, kind="class",
        defined_in=str(mod.path.relative_to(ROOT)).replace("\\", "/"), line=node.lineno,
        decorators=[_seg(mod, d) for d in node.decorator_list],
        bases=[_seg(mod, b) for b in node.bases])
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) \
                and not item.target.id.startswith("_"):
            sym.fields.append(Param(item.target.id, _seg(mod, item.annotation),
                                    _seg(mod, item.value) if item.value else None, "field"))
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name.startswith("_") and item.name not in ("__init__", "__call__"):
                continue
            sym.methods.append(_function(mod, item, f"{qual}.{item.name}", in_class=True))
    return sym


def _constant(mod: Module, node: ast.Assign | ast.AnnAssign, name: str, qual: str) -> Symbol:
    value = _seg(mod, node.value)
    if len(value) > VALUE_MAX:
        value = value[: VALUE_MAX - 3] + "..."
    ann = _seg(mod, node.annotation) if isinstance(node, ast.AnnAssign) else ""
    return Symbol(qual=qual, module=mod.qual, name=name, kind="constant",
                  defined_in=str(mod.path.relative_to(ROOT)).replace("\\", "/"),
                  line=node.lineno, value=value, annotation=ann)


def _top_level(mod: Module) -> dict[str, ast.AST]:
    found: dict[str, ast.AST] = {}
    for node in mod.tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found[node.name] = node
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    found[t.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found[node.target.id] = node
    return found


def _build(mods: dict[str, Module], defmod: str, name: str, qual: str) -> Symbol | None:
    mod = mods.get(defmod)
    if mod is None:
        return None
    node = _top_level(mod).get(name)
    if node is None:
        # Re-exported through a chain: follow the import one more step.
        if name in mod.imports:
            src_mod, src_name = mod.imports[name]
            return _build(mods, src_mod, src_name, qual)
        return None
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        sym = _function(mod, node, qual)
    elif isinstance(node, ast.ClassDef):
        sym = _class(mod, node, qual)
    elif isinstance(node, (ast.Assign, ast.AnnAssign)):
        sym = _constant(mod, node, name, qual)
    else:
        return None
    sym.name = qual.rsplit(".", 1)[1]
    sym.module = qual.rsplit(".", 1)[0]
    return sym


def discover() -> tuple[dict[str, Module], dict[str, list[Symbol]]]:
    """Public modules and their symbols, each symbol under its import path."""
    mods = load_modules()
    covered: set[tuple[str, str]] = set()   # (defining module, name) documented above
    out: dict[str, list[Symbol]] = {}
    # Packages first, so a package's __all__ claims its re-exports before the
    # submodule that defines them is visited.
    order = sorted(mods, key=lambda q: (mods[q].path.name != "__init__.py", q))
    for qual in order:
        mod = mods[qual]
        if _is_private_module(qual):
            continue
        names: list[str]
        if mod.all_names is not None:
            names = list(mod.all_names)
        else:
            names = []
            for name, node in _top_level(mod).items():
                if name.startswith("_"):
                    continue
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                        or name.isupper():
                    names.append(name)
            names += EXTRA_PUBLIC.get(qual, [])
        syms: list[Symbol] = []
        for name in names:
            if name in mod.imports and name not in _top_level(mod):
                src_mod, src_name = mod.imports[name]
                key = (src_mod, src_name)
            else:
                src_mod, src_name, key = qual, name, (qual, name)
            if key in covered:
                continue
            sym = _build(mods, src_mod, src_name, f"{qual}.{name}")
            if sym is None:
                continue
            covered.add(key)
            syms.append(sym)
        # A module whose names are all re-exported by its package gets no
        # section of its own; the package's module block names it.
        if syms:
            out[qual] = sorted(syms, key=lambda s: (_KIND_ORDER[s.kind], s.name.lower()))
    return mods, {q: out[q] for q in sorted(out)}


_KIND_ORDER = {"function": 0, "class": 1, "constant": 2}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _signature(sym: Symbol) -> str:
    parts: list[str] = []
    saw_kw_marker = False
    for i, p in enumerate(sym.params):
        if p.kind == "kw-only" and not saw_kw_marker and not any(
                q.kind == "var-positional" for q in sym.params[:i]):
            parts.append("*")
            saw_kw_marker = True
        text = p.name + (f": {p.annotation}" if p.annotation else "")
        if p.default is not None:
            text += f" = {p.default}" if p.annotation else f"={p.default}"
        parts.append(text)
        if p.kind == "pos-only" and (i + 1 == len(sym.params)
                                     or sym.params[i + 1].kind != "pos-only"):
            parts.append("/")
    head = ("async def " if sym.is_async else "def ") + sym.name
    sig = f"{head}({', '.join(parts)})"
    return sig + (f" -> {sym.returns}" if sym.returns else "")


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _uncell(text: str) -> str:
    return text.replace("\\|", "|")


def _param_rows(params: list[Param], kept: dict[str, str], header: str) -> list[str]:
    rows = [f"| {header} | Type | Default | Purpose |", "|---|---|---|---|"]
    for p in params:
        default = "required" if p.default is None and p.kind in ("pos-only", "normal",
                                                                 "kw-only", "field") \
            else ("-" if p.default is None else f"`{_cell(p.default)}`")
        if p.kind == "kw-only":
            default += " (keyword-only)"
        elif p.kind == "pos-only":
            default += " (positional-only)"
        purpose = kept.get(p.name, TODO)
        ann = f"`{_cell(p.annotation)}`" if p.annotation else "-"
        rows.append(f"| `{p.name}` | {ann} | {default} | {purpose} |")
    return rows


def _parse_kept(body: str) -> dict[str, str]:
    """Purpose cells and the Returns text from an existing block, by key."""
    kept: dict[str, str] = {}
    for line in body.splitlines():
        # Split on unescaped pipes only: a purpose or a type may contain "\|".
        cells = re.split(r"(?<!\\)\|", line)
        if line.startswith("| `") and len(cells) >= 4:
            m = re.match(r"\s*`([^`]+)`\s*$", cells[1])
            if m:
                kept[m.group(1)] = cells[-2].strip()
        m = re.match(r"\*\*Returns\*\* .*? -- (?P<text>.*)$", line)
        if m:
            kept["->"] = m.group("text").strip()
        m = re.match(r"\*\*Value\*\* .*? -- (?P<text>.*)$", line)
        if m:
            kept["="] = m.group("text").strip()
    return kept


def render_block(sym: Symbol, kept: dict[str, str]) -> str:
    lines: list[str] = []
    # No line number: any edit above a symbol would make the dictionary
    # stale with no API change, and the check would cry wolf.
    loc = f"`{sym.defined_in}`"
    if sym.kind == "function":
        lines += ["```python", _signature(sym), "```", "", f"Defined in {loc}.", ""]
        if sym.params:
            lines += _param_rows(sym.params, kept, "Parameter") + [""]
        else:
            lines += ["No parameters.", ""]
        ret = f"`{sym.returns}`" if sym.returns else "not annotated"
        lines.append(f"**Returns** {ret} -- {kept.get('->', TODO)}")
    elif sym.kind == "class":
        head = f"class {sym.name}" + (f"({', '.join(sym.bases)})" if sym.bases else "")
        decos = [f"@{d}" for d in sym.decorators]
        lines += ["```python", *decos, head, "```", "", f"Defined in {loc}.", ""]
        if sym.fields:
            lines += _param_rows(sym.fields, kept, "Field") + [""]
        if sym.methods:
            lines += ["| Method | Signature | Purpose |", "|---|---|---|"]
            for m in sym.methods:
                tag = " (property)" if "property" in m.decorators else ""
                lines.append(f"| `{m.name}` | `{_cell(_signature(m))}`{tag} | "
                             f"{kept.get(m.name, TODO)} |")
            lines.append("")
        if lines[-1] == "":
            lines.pop()
    else:
        ann = f": {sym.annotation}" if sym.annotation else ""
        lines += [f"Defined in {loc}.", "",
                  f"**Value** `{sym.name}{_cell(ann)} = {_cell(sym.value)}` -- "
                  f"{kept.get('=', TODO)}"]
    return "\n".join(lines) + "\n"


def render_module_block(mod: Module, syms: list[Symbol]) -> str:
    rel = str(mod.path.relative_to(ROOT)).replace("\\", "/")
    counts = {k: sum(1 for s in syms if s.kind == k) for k in ("function", "class", "constant")}
    plural = {"function": "functions", "class": "classes", "constant": "constants"}
    public = ", ".join(f"{n} {k if n == 1 else plural[k]}" for k, n in counts.items() if n)
    declared = "declared by `__all__`" if mod.all_names is not None else \
        "no `__all__`: every top-level name without a leading underscore"
    line = f"Source `{rel}`. Public names: {public} ({declared})."
    others = sorted({s.defined_in for s in syms} - {rel})
    if others:
        line += (" Some are defined in, and also importable from: "
                 + ", ".join(f"`{o}`" for o in others) + ".")
    return line + "\n"


def skeleton(sym: Symbol) -> str:
    label = {"function": "", "class": " (class)", "constant": " (constant)"}[sym.kind]
    # A constant's Value line carries its purpose; a Does line would repeat it.
    does = "" if sym.kind == "constant" else f"**Does.** {TODO}\n\n"
    return (f"### `{sym.name}`{label}\n\n<!-- dict:{sym.qual} -->\n"
            f"{render_block(sym, {})}<!-- /dict -->\n\n{does}")


def module_skeleton(mod: Module, syms: list[Symbol]) -> str:
    return (f"## `{mod.qual}`\n\n<!-- dict-module:{mod.qual} -->\n"
            f"{render_module_block(mod, syms)}<!-- /dict-module -->\n\n"
            f"**Purpose.** {TODO}\n\n**Use it when.** {TODO}\n\n"
            f"**Do not use it when.** {TODO}\n\n")


def _does(text: str, qual: str) -> str:
    """First sentence of the entry's 'Does.' line, for the index."""
    start = text.find(f"<!-- dict:{qual} -->")
    if start < 0:
        return TODO
    # Only this entry: a missing 'Does.' must not borrow the next entry's.
    nxt = re.search(r"^#{2,3} ", text[start:], re.M)
    entry = text[start:start + nxt.start()] if nxt else text[start:]
    m = re.search(r"\*\*Does\.\*\* (.+)", entry) or \
        re.search(r"^\*\*Value\*\* .*? -- (.+)$", entry, re.M)
    if not m:
        return TODO
    line = m.group(1).strip()
    first = re.split(r"(?<=[.!?])\s", line, maxsplit=1)[0]
    return first


def render_index(text: str, symbols: dict[str, list[Symbol]]) -> str:
    rows = ["| Name | Kind | Does |", "|---|---|---|"]
    for syms in symbols.values():
        for s in syms:
            anchor = f"[`{s.qual}`](#{_anchor(s)})"
            rows.append(f"| {anchor} | {s.kind} | {_cell(_does(text, s.qual))} |")
    return "\n".join(rows) + "\n"


def _anchor(sym: Symbol) -> str:
    # GitHub's heading anchors: lowercase, punctuation dropped, spaces to '-'.
    label = {"function": "", "class": " (class)", "constant": " (constant)"}[sym.kind]
    heading = f"{sym.name}{label}".lower()
    return re.sub(r"[^\w\- ]", "", heading).replace(" ", "-")


def pyproject_version() -> str:
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"',
                  (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if not m:
        raise SystemExit("no version in pyproject.toml")
    return m.group(1)


# ---------------------------------------------------------------------------
# Write and check
# ---------------------------------------------------------------------------

def _module_span(text: str, qual: str) -> tuple[int, int] | None:
    m = re.search(rf"^## `{re.escape(qual)}`\n", text, re.M)
    if not m:
        return None
    nxt = re.search(r"^## ", text[m.end():], re.M)
    return m.start(), (m.end() + nxt.start()) if nxt else len(text)


def regenerate(text: str) -> tuple[str, list[str]]:
    """Return the refreshed text and the notes about what was added."""
    mods, symbols = discover()
    notes: list[str] = []
    by_qual = {s.qual: s for syms in symbols.values() for s in syms}

    def block(m: re.Match[str]) -> str:
        sym = by_qual.get(m.group("qual"))
        if sym is None:
            return m.group(0)  # reported by check(); a human writes the removal note
        kept = _parse_kept(m.group("body"))
        return f"<!-- dict:{sym.qual} -->\n{render_block(sym, kept)}<!-- /dict -->"

    text = BLOCK_RE.sub(block, text)

    def modblock(m: re.Match[str]) -> str:
        q = m.group("qual")
        if q not in mods or q not in symbols:
            return m.group(0)
        return (f"<!-- dict-module:{q} -->\n{render_module_block(mods[q], symbols[q])}"
                f"<!-- /dict-module -->")

    text = MODULE_RE.sub(modblock, text)

    for qual, syms in symbols.items():
        span = _module_span(text, qual)
        if span is None:
            at = text.find("\n## Specs")
            at = len(text) if at < 0 else at + 1
            text = text[:at] + module_skeleton(mods[qual], syms) + text[at:]
            notes.append(f"added module section {qual}")
            span = _module_span(text, qual)
            assert span is not None
        for s in syms:
            if f"<!-- dict:{s.qual} -->" in text:
                continue
            _, end = span
            text = text[:end] + skeleton(s) + text[end:]
            notes.append(f"added skeleton {s.qual}")
            span = _module_span(text, qual)
            assert span is not None

    m = INDEX_RE.search(text)
    if m:
        text = text[:m.start()] + f"<!-- dict-index -->\n{render_index(text, symbols)}" \
            f"<!-- /dict-index -->" + text[m.end():]
    m = VERSION_RE.search(text)
    if m:
        text = text[:m.start()] + f"<!-- dict-version -->{pyproject_version()}" \
            f"<!-- /dict-version -->" + text[m.end():]
    return text, notes


def check(text: str) -> list[str]:
    problems: list[str] = []
    mods, symbols = discover()
    fresh, notes = regenerate(text)
    problems += [f"missing: {n.split(' ', 2)[-1]} has no entry" for n in notes]
    quals = {s.qual for syms in symbols.values() for s in syms}
    for m in BLOCK_RE.finditer(text):
        if m.group("qual") not in quals:
            problems.append(f"stale entry: {m.group('qual')} is not a public symbol")
    for m in MODULE_RE.finditer(text):
        if m.group("qual") not in symbols:
            problems.append(f"stale module section: {m.group('qual')}")
    if not notes and fresh != text:
        problems.append("generated blocks are out of date: run tools/gen_dictionary.py --write")
    for m in BLOCK_RE.finditer(fresh):
        for line in m.group("body").splitlines():
            if line.rstrip().endswith(f"| {TODO} |") or line.rstrip().endswith(f"-- {TODO}"):
                problems.append(f"undocumented: {m.group('qual')}: {line.strip()[:70]}")
    for qual in quals:
        if f"<!-- dict:{qual} -->" in fresh and _does(fresh, qual) in (TODO, ""):
            problems.append(f"undocumented: {qual} has no 'Does.' line")
    for qual in symbols:
        span = _module_span(fresh, qual)
        if span is None:
            continue
        section = fresh[span[0]:span[1]]
        for label in ("**Purpose.**", "**Use it when.**", "**Do not use it when.**"):
            # The text may follow on the same line or as bullets below it;
            # it runs to the next bold label or heading.
            m2 = re.search(re.escape(label) + r"(.*?)(?=\n\*\*[A-Z][^*]*\.\*\*|\n#|\Z)",
                           section, re.S)
            if not m2 or m2.group(1).strip() in ("", TODO):
                problems.append(f"undocumented: module {qual}: {label}")
    version = pyproject_version()
    if not VERSION_RE.search(text):
        problems.append("no <!-- dict-version --> marker")
    if not re.search(rf"^### {re.escape(version)}\b", text, re.M):
        problems.append(f"no '### {version}' heading in Changes: every release says "
                        f"what changed for consumers")
    if not INDEX_RE.search(text):
        problems.append("no <!-- dict-index --> marker")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    text = DICT.read_text(encoding="utf-8") if DICT.exists() else ""
    if args.write:
        fresh, notes = regenerate(text)
        DICT.write_text(fresh, encoding="utf-8", newline="\n")
        for n in notes:
            print(n)
        todo = fresh.count(TODO)
        print(f"wrote {DICT.name}; {todo} TODO marker(s) left")
        return 0
    problems = check(text)
    for p in problems:
        print(p)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
