"""XML <-> JSON under the MovieLabs MDDF JSON Encoding Best Practice.

One converter for the portfolio (eidr-core 0.70.0). XML_to_JSON's standard
output, python-sdk's codec and python-tools' ``-f json`` each had their own
XML-to-JSON rules, and all three disagreed with the practice and with each
other (eidr-core-ops ``MDDF-JSON-BP-ASSESSMENT-2026-11-11.md``). This module
is the practice, as written in Draft 3 with EIDR's redline (RWK-v3, submitted
to MovieLabs 2026-11-11), and ``specs/mddf-json.md`` states every rule with
its worked example. Built from python-sdk's ``eidr.codecs`` (its key and
attribute conventions), with cardinality taken per parent type from the
schema instead of from a name list.

* ``xml_to_json`` -- XML text/bytes to a JSON-ready ``dict``.
* ``json_to_xml`` -- the reverse, in schema order.
* ``embed_xml`` -- Section 2: the XML itself as a JSON string value, keyed by
  its root element's name (e.g. ``CoreMetadata``). Signed XML travels this
  way, beside its translation or alone.
* ``eidr_schema`` -- the EIDR 2.7.0 schema set (with EIDR's md 2.8), the
  newest EIDR has published; the registry reports 2.7.1, which is not
  published.
* ``dumps`` -- the canonical byte form (pretty or compact) the conformance
  corpus compares.

Not here: XML_to_JSON's internal records (it renders those to the practice's
shape itself) and the star JSONL, which the operator locked (2026-11-11).
"""
from __future__ import annotations

import io
import json
import re
import warnings
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from ._schema import ContentModel, SchemaSet, TypeRef

__all__ = [
    "MddfJsonError",
    "MddfJsonWarning",
    "SchemaSet",
    "SignedXmlError",
    "dumps",
    "eidr_schema",
    "embed_xml",
    "is_signed",
    "json_to_xml",
    "xml_to_json",
]

XSI = "http://www.w3.org/2001/XMLSchema-instance"
XML_NS = "http://www.w3.org/XML/1998/namespace"
DSIG = "http://www.w3.org/2000/09/xmldsig#"
VALUE = "value"
# The practice trims exactly these four (space, tab, CR, LF), not all Unicode
# white space: a no-break space at the edge of a title is content.
_TRIM = " \t\r\n"

_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
_EIDR_FILES = ("common.xsd", "api-common.xsd", "api.xsd", "service.xsd", "md-v28-eidr.xsd",
               "doi.xsd", "doiavs.xsd", "iso3166a2.xsd")


class MddfJsonError(ValueError):
    """The input cannot be translated under the practice."""


class SignedXmlError(MddfJsonError):
    """The XML is signed and the caller did not say the signed XML travels with it."""


class MddfJsonWarning(UserWarning):
    """An element the schema does not declare: its cardinality was observed, not known."""


@lru_cache(maxsize=1)
def eidr_schema() -> SchemaSet:
    """EIDR schema 2.7.0 with EIDR's md 2.8 (redefinitions applied), cached.

    The same files python-sdk bundles (``MANIFEST.json`` beside them carries
    their sha256), restricted to the set the registry's API and record XML
    import. The practice: "the most recent published version for the
    namespace" -- EIDR's namespace is unversioned, so this file set IS the
    version, and replacing it changes the output for every caller at once.
    """
    return SchemaSet([_SCHEMA_DIR / "eidr-2.7.0" / f for f in _EIDR_FILES], label="EIDR 2.7.0")


# ---------------------------------------------------------------------------
# Instance tree with prefixes (ElementTree drops them; the practice needs them)
# ---------------------------------------------------------------------------

@dataclass
class _Node:
    qname: str
    attrs: dict[str, str]
    decls: list[tuple[str, str]]          # (prefix, uri) declared ON this element
    scope: dict[str, str]                 # prefix -> uri in scope here
    text: str = ""
    children: list[_Node] = field(default_factory=list)


def _parse(xml: str | bytes) -> _Node:
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    stack: list[_Node] = []
    pending: list[tuple[str, str]] = []
    root: _Node | None = None
    elems: list[ET.Element] = []
    for event, item in ET.iterparse(io.BytesIO(data), events=("start-ns", "start", "end")):
        if event == "start-ns":
            pending.append(item)  # type: ignore[arg-type]
        elif event == "start":
            el: ET.Element = item  # type: ignore[assignment]
            scope = dict(stack[-1].scope) if stack else {"xml": XML_NS}
            for p, uri in pending:
                scope[p] = uri
            node = _Node(el.tag, dict(el.attrib), pending, scope)
            pending = []
            if stack:
                stack[-1].children.append(node)
            else:
                root = node
            stack.append(node)
            elems.append(el)
        else:
            el = elems.pop()
            node = stack.pop()
            # Text is the element's own text plus every child's tail: mixed
            # content keeps its characters even though the practice has no
            # place for their positions.
            node.text = (el.text or "") + "".join(c.tail or "" for c in el)
            # No el.clear(): it would reset the children's tails, which the
            # parent's text still needs. Registry documents are small.
    assert root is not None
    return root


def _split(qname: str) -> tuple[str, str]:
    if qname.startswith("{"):
        ns, local = qname[1:].split("}", 1)
        return ns, local
    return "", qname


def _prefix_for(node: _Node, ns: str) -> str | None:
    # The nearest declaration wins; with two prefixes bound to one namespace
    # the later one is the one in scope here.
    found = None
    for p, uri in node.scope.items():
        if uri == ns:
            found = p
    return found


def _prefixed(node: _Node, qname: str) -> str:
    ns, local = _split(qname)
    if not ns:
        return local
    p = _prefix_for(node, ns)
    if p is None:
        raise MddfJsonError(f"no prefix in scope for namespace {ns!r}")
    return f"{p}:{local}" if p else local


def _trim(s: str | None) -> str | None:
    if s is None:
        return None
    t = s.strip(_TRIM)
    return t if t else None


def is_signed(xml: str | bytes) -> bool:
    """True when the XML carries an XML Signature (``ds:Signature``) anywhere."""
    return any(n == f"{{{DSIG}}}Signature" for n in _iter_qnames(_parse(xml)))


def _iter_qnames(node: _Node):
    yield node.qname
    for c in node.children:
        yield from _iter_qnames(c)


_VERSION_IN_NS = re.compile(r"/v(\d+(?:\.\d+)+)(?:/|$)")
_VERSION_IN_LOC = re.compile(r"v?(\d+(?:[._]\d+)+)\.xsd$")


def _check_schema_location(root: _Node) -> None:
    """Practice 3.1 (EIDR redline E6): a version may be named by a versioned
    namespace or by xsi:schemaLocation; if both name one and they disagree, the
    XML is in error."""
    loc = root.attrs.get(f"{{{XSI}}}schemaLocation")
    if not loc:
        return
    parts = loc.split()
    for ns, where in zip(parts[0::2], parts[1::2], strict=False):
        a, b = _VERSION_IN_NS.search(ns), _VERSION_IN_LOC.search(where)
        if a and b and a.group(1) != b.group(1).replace("_", "."):
            raise MddfJsonError(
                f"xsi:schemaLocation names {where!r} (version {b.group(1)}) for namespace {ns!r} "
                f"(version {a.group(1)}); the two must agree")


# ---------------------------------------------------------------------------
# XML -> JSON
# ---------------------------------------------------------------------------

def xml_to_json(xml: str | bytes, *, schema: SchemaSet | None = None, api: bool = False,
                omit_namespaces: bool = False, allow_signed: bool = False,
                strict: bool = False) -> dict[str, Any]:
    """Translate one XML document to the practice's JSON (a ``dict``).

    ``api=False`` (standalone document): the root element is kept as the one
    top-level key. ``api=True``: the root is removed and its attributes and
    namespace declarations become the top-level object's (EIDR redline E1:
    ManifestID, updateNum and xsi:schemaLocation are kept too, so nothing is
    lost); ``omit_namespaces=True`` drops the root's declarations, which the
    practice allows only when the API documents the version.

    Signed XML raises :class:`SignedXmlError` unless ``allow_signed=True``:
    the translation does not carry the signature, so the caller must deliver
    the signed XML with it (``embed_xml`` or a separate document) and says so
    by passing the flag.

    An element the schema does not allow where it occurs is keyed by its local
    name with its cardinality observed (repeated siblings -> array) and an
    :class:`MddfJsonWarning`; ``strict=True`` raises instead. Lenient is the
    default because the registry can serve a schema version newer than the
    newest one published.
    """
    sch = schema or eidr_schema()
    root = _parse(xml)
    if not allow_signed and any(q == f"{{{DSIG}}}Signature" for q in _iter_qnames(root)):
        raise SignedXmlError("signed XML: translate with allow_signed=True and deliver the "
                             "signed XML with the JSON (embed_xml, or a separate document)")
    _check_schema_location(root)
    if sch.has_element(root.qname):
        rtype = sch.element_type(root.qname)
    else:
        where = sch.label or "the schema"
        _unknown(strict, f"root element {root.qname} is not declared in {where}")
        rtype = None
    known = sch.has_element(root.qname)
    body = _element(root, rtype, sch, strict, known, omit_decls=api and omit_namespaces)
    if api:
        if body is None:
            return {}
        if not isinstance(body, dict):
            return {VALUE: body}
        return body
    return {_split(root.qname)[1]: body}


def _unknown(strict: bool, msg: str) -> None:
    if strict:
        raise MddfJsonError(msg)
    warnings.warn(msg, MddfJsonWarning, stacklevel=3)


def _attributes(node: _Node, omit_decls: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not omit_decls:
        for p, uri in node.decls:
            out["_xmlns:" + p if p else "_xmlns"] = uri
    for q, v in node.attrs.items():
        ns, local = _split(q)
        key = "_" + (_prefixed(node, q) if ns else local)
        out[key] = _trim(v)
    return out


def _is_nil(node: _Node) -> bool:
    v = node.attrs.get(f"{{{XSI}}}nil")
    return v is not None and v.strip(_TRIM) in ("true", "1")


def _element(node: _Node, typ: TypeRef, sch: SchemaSet, strict: bool, known: bool,
             omit_decls: bool = False) -> Any:
    # xsi:type names the type that governs this element's content (EIDR's
    # AlternateID); it is also kept as an attribute ("_xsi:type").
    xt = node.attrs.get(f"{{{XSI}}}type")
    if xt:
        p, _, local = xt.strip(_TRIM).rpartition(":")
        q = "{{{}}}{}".format(node.scope.get(p, ""), local)
        if sch.has_type(q):
            typ = q
    attrs = _attributes(node, omit_decls)
    if _is_nil(node) and set(attrs) == {_attr_key(node, f"{{{XSI}}}nil")}:
        return None
    model = sch.content(typ) if known else ContentModel()
    text = _trim(node.text)
    if not node.children:
        if not attrs:
            return text
        # Simple content with attributes: the text under "value", then the
        # attributes (the practice's example order). Content that is empty
        # after trimming is no content: the object carries only attributes.
        return {VALUE: text, **attrs} if text is not None else attrs
    out: dict[str, Any] = dict(attrs)
    if text is not None:
        out[VALUE] = text
    groups: dict[str, list[_Node]] = {}
    for c in node.children:
        groups.setdefault(c.qname, []).append(c)
    used_keys: dict[str, str] = {}
    for q, nodes in groups.items():
        ns, local = _split(q)
        child = model.children.get(q)
        if child is not None:
            key, multi, ctype, cknown = local, child.max > 1, child.type, True
        else:
            wc = next((w for w in model.wildcards if w.admits(ns)), None)
            if wc is not None:
                # Practice 3.1: a wildcard element keeps its prefix, because
                # nothing in the schema names its namespace.
                key = _prefixed(nodes[0], q)
                multi = wc.max > 1
                cknown = sch.has_element(q)
                ctype = sch.element_type(q) if cknown else None
            else:
                if known and not model.simple:
                    _unknown(strict, f"{local!r} is not allowed in {_split(node.qname)[1]!r} "
                                     f"by {sch.label or 'the schema'}; cardinality observed")
                key, multi, ctype, cknown = local, len(nodes) > 1, None, False
        if key in used_keys:
            raise MddfJsonError(f"two child elements of {_split(node.qname)[1]!r} share the key "
                                f"{key!r} ({used_keys[key]} and {q})")
        used_keys[key] = q
        if not multi and len(nodes) > 1 and (strict or cknown):
            raise MddfJsonError(f"{local!r} occurs {len(nodes)} times in "
                                f"{_split(node.qname)[1]!r}; the schema allows one")
        vals = [_element(n, ctype, sch, strict, cknown) for n in nodes]
        out[key] = vals if multi or len(vals) > 1 else vals[0]
    return out


def _attr_key(node: _Node, qname: str) -> str:
    return "_" + _prefixed(node, qname)


# ---------------------------------------------------------------------------
# JSON -> XML
# ---------------------------------------------------------------------------

def json_to_xml(obj: dict[str, Any], *, schema: SchemaSet | None = None,
                root: str | None = None, namespaces: dict[str, str] | None = None,
                xml_declaration: bool = True) -> str:
    """Translate the practice's JSON back to XML.

    Children are written in schema order (the JSON keeps sibling order only
    within one name). A null element becomes ``<X/>`` and a null attribute
    ``x=""`` (operator, 2026-11-11): the reverse reproduces content, not form.

    Standalone JSON has one top-level key, the root's local name. API JSON
    has none: pass ``root`` (``"{namespace}Local"``). Declarations come from
    the ``_xmlns`` keys; ``namespaces`` (prefix -> URI) supplies them when the
    API omitted them.
    """
    sch = schema or eidr_schema()
    if root is None:
        if len(obj) != 1:
            raise MddfJsonError("standalone JSON has exactly one top-level key; "
                                "pass root= for API JSON")
        (local, body), = obj.items()
        decls = body if isinstance(body, dict) else {}
        ns = _root_namespace(sch, local, decls, namespaces)
        rq = f"{{{ns}}}{local}"
    else:
        rq, body = root, obj
    scope = {"xml": XML_NS}
    extra = dict(namespaces or {})
    out: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>'] if xml_declaration else []
    _write(out, rq, body, sch.element_type(rq) if sch.has_element(rq) else None, sch, scope,
           extra, sch.has_element(rq), top=True)
    return "".join(out)


def _root_namespace(sch: SchemaSet, local: str, body: dict, given: dict[str, str] | None) -> str:
    candidates = [q for q in sch.elements if _split(q)[1] == local]
    default = body.get("_xmlns") or (given or {}).get("")
    if default and f"{{{default}}}{local}" in sch.elements:
        return default
    if len(candidates) == 1:
        return _split(candidates[0])[0]
    if default:
        return default
    raise MddfJsonError(f"cannot tell which namespace root {local!r} is in; pass root=")


def _write(out: list[str], qname: str, value: Any, typ: TypeRef, sch: SchemaSet,
           scope: dict[str, str], extra: dict[str, str], known: bool, top: bool = False) -> None:
    scope = dict(scope)
    decls: list[tuple[str, str]] = []
    attrs: list[tuple[str, str]] = []
    children: list[tuple[str, Any]] = []
    text: str | None = None
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "_xmlns" or k.startswith("_xmlns:"):
                p = k[7:] if k.startswith("_xmlns:") else ""
                scope[p] = "" if v is None else str(v)
                decls.append((p, scope[p]))
            elif k.startswith("_"):
                attrs.append((k[1:], "" if v is None else _scalar(v)))
            elif k == VALUE:
                text = None if v is None else _scalar(v)
            else:
                children.append((k, v))
    elif value is not None:
        text = _scalar(value)
    # A namespace the JSON needs but never declared (API JSON with its
    # declarations omitted): declare it on the root from namespaces=, else
    # from the schema's conventional prefix.
    ns, local = _split(qname)
    if top:
        for p, uri in extra.items():
            if scope.get(p) != uri:
                scope[p] = uri
                decls.append((p, uri))
    tag = _qname_text(ns, local, scope, decls, sch)
    for q in [a for a, _ in attrs if ":" in a]:
        p = q.split(":", 1)[0]
        if p not in scope:
            # Only xsi can be supplied unasked: its URI is fixed by the
            # standard, and Draft-2-era JSON often lacked the declaration.
            if p != "xsi":
                raise MddfJsonError(f"attribute prefix {p!r} is not declared")
            scope[p] = XSI
            decls.append((p, XSI))
    model = sch.content(_xsi_type(attrs, scope, sch) or typ) if known else ContentModel()
    parts = [f"<{tag}"]
    for p, uri in decls:
        parts.append(f" xmlns:{p}={quoteattr(uri)}" if p else f" xmlns={quoteattr(uri)}")
    for name, v in attrs:
        parts.append(f" {name}={quoteattr(v)}")
    ordered = _schema_order(children, model, ns, scope)
    if text is None and not ordered:
        parts.append("/>")
        out.append("".join(parts))
        return
    parts.append(">")
    out.append("".join(parts))
    if text is not None:
        out.append(escape(text))
    for cq, cval, ctype, cknown in ordered:
        for item in (cval if isinstance(cval, list) else [cval]):
            _write(out, cq, item, ctype, sch, scope, {}, cknown)
    out.append(f"</{tag}>")


def _scalar(v: Any) -> str:
    # Draft-2-era JSON carried numbers and booleans; XML wants their text.
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _xsi_type(attrs: list[tuple[str, str]], scope: dict[str, str], sch: SchemaSet) -> str | None:
    for name, v in attrs:
        if name.endswith(":type") and scope.get(name.split(":", 1)[0]) == XSI:
            p, _, local = v.rpartition(":")
            q = "{{{}}}{}".format(scope.get(p, ""), local)
            if sch.has_type(q):
                return q
    return None


def _qname_text(ns: str, local: str, scope: dict[str, str], decls: list[tuple[str, str]],
                sch: SchemaSet) -> str:
    if not ns:
        return local
    for p, uri in reversed(list(scope.items())):
        if uri == ns:
            return f"{p}:{local}" if p else local
    p = sch.prefixes.get(ns) or "ns"
    while p in scope:
        p += "x"
    scope[p] = ns
    decls.append((p, ns))
    return f"{p}:{local}"


def _schema_order(children: list[tuple[str, Any]], model: ContentModel, parent_ns: str,
                  scope: dict[str, str]) -> list[tuple[str, Any, TypeRef, bool]]:
    placed: list[tuple[float, int, str, Any, TypeRef, bool]] = []
    for i, (key, val) in enumerate(children):
        if ":" in key:
            p, local = key.split(":", 1)
            if p not in scope:
                raise MddfJsonError(f"key {key!r}: prefix {p!r} is not declared")
            q = f"{{{scope[p]}}}{local}"
            hit = model.children.get(q)
            pos = hit.position if hit else min((w.position for w in model.wildcards), default=10**6)
            placed.append((pos, i, q, val, hit.type if hit else None, hit is not None))
            continue
        hits = model.by_local(key)
        if len(hits) > 1:
            raise MddfJsonError(f"key {key!r} matches {len(hits)} elements in the schema")
        if hits:
            placed.append((hits[0].position, i, hits[0].qname, val, hits[0].type, True))
        else:
            # Unknown to the schema: the parent's namespace (an unprefixed key
            # is an element the schema would have declared), after the known.
            placed.append((10**6, i, f"{{{parent_ns}}}{key}", val, None, False))
    placed.sort(key=lambda t: (t[0], t[1]))
    return [(q, v, t, k) for _, _, q, v, t, k in placed]


# ---------------------------------------------------------------------------
# Embedding (Section 2) and the canonical byte form
# ---------------------------------------------------------------------------

def embed_xml(xml: str | bytes, name: str | None = None) -> dict[str, str]:
    """Section 2: ``{"<RootElement>": "<the XML, unchanged>"}``.

    The practice recommends the element's own name as the key (EIDR chose it,
    2026-11-11: ``CoreMetadata`` for a MEC CoreMetadata). The text is kept
    exactly, white space included: that is what keeps a signature verifiable.
    JSON escaping (quotes, backslashes, control characters) is the
    serializer's job, as ``json.dumps`` does it.
    """
    text = xml.decode("utf-8") if isinstance(xml, bytes) else xml
    if name is None:
        name = _split(_parse(text).qname)[1]
    return {name: text}


def dumps(obj: Any, *, pretty: bool = True) -> str:
    """The byte form the conformance corpus compares: UTF-8 characters kept
    (``ensure_ascii=False``), two-space indent when pretty, no spaces when
    compact, key order as built."""
    if pretty:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
