"""The part of an XML Schema the MDDF JSON practice needs: which child
elements a type allows, how many times, of which type, and in which order.

The practice decides arrays by the schema, not by the instance: "Cardinality is
determined by the element's definition in the schema, not by the number of
instances in the XML." That definition is per PARENT TYPE. python-sdk's codec
harvested one name-based set across every bundled XSD, so a name that repeats
anywhere repeated everywhere (`Parent`, `md:DisplayName`): wrong for the types
where it is single. This model answers per type instead.

Deliberately small. It reads complexType / sequence / choice / all / group /
element / any, complexContent extension and restriction, and simpleContent; it
ignores attributes (the instance supplies them), facets, identity constraints
and xs:redefine (the EIDR set ships md-v28-eidr.xsd, in which EIDR's
redefinitions are already applied, so nothing here needs redefine). Stdlib
ElementTree only, so the module stays vendorable.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

XS = "http://www.w3.org/2001/XMLSchema"
_XS = f"{{{XS}}}"

# A type reference: a named type's QName ("{ns}local"), or an anonymous
# complexType node, or None for a simple/unknown type (no element children).
TypeRef = Union[str, ET.Element, None]  # noqa: UP007 (runtime alias; 3.10 floor)


@dataclass
class Child:
    """One child element a content model allows."""

    qname: str               # "{namespace}local"
    max: float               # effective maxOccurs: own x every enclosing compositor
    type: TypeRef
    position: int            # first position in the content model (JSON->XML order)


@dataclass
class Wildcard:
    """An xs:any: which namespaces it admits, and how often."""

    namespaces: str          # the xs:any/@namespace value ("##other", "##any", a list)
    target: str              # the declaring schema's targetNamespace (for ##other/##local)
    max: float
    position: int

    def admits(self, ns: str) -> bool:
        spec = self.namespaces.split()
        if not spec or "##any" in spec:
            return True
        if spec == ["##other"]:
            return ns not in ("", self.target)
        allowed = {self.target if s == "##targetNamespace" else "" if s == "##local" else s
                   for s in spec}
        return ns in allowed


@dataclass
class ContentModel:
    children: dict[str, Child] = field(default_factory=dict)
    wildcards: list[Wildcard] = field(default_factory=list)
    simple: bool = False     # simpleContent or a simple type: text, no element children

    def by_local(self, local: str) -> list[Child]:
        return [c for c in self.children.values() if c.qname.rsplit("}", 1)[-1] == local]


def _max(node: ET.Element) -> float:
    v = node.get("maxOccurs", "1")
    return math.inf if v == "unbounded" else float(int(v))


@dataclass
class _Doc:
    target: str
    prefixes: dict[str, str]          # prefix -> namespace URI, as declared in the XSD
    qualified: bool                   # elementFormDefault="qualified"


class SchemaSet:
    """Global element and type definitions from a set of XSD files.

    Every file is loaded regardless of include/import (their schemaLocation is
    not followed), so the set is exactly the files given: which schema version
    governs is the caller's choice, made by choosing the files.
    """

    def __init__(self, files: Iterable[str | Path], *, label: str = ""):
        self.label = label
        self.elements: dict[str, tuple[ET.Element, _Doc]] = {}
        self.types: dict[str, tuple[ET.Element, _Doc]] = {}
        self.groups: dict[str, tuple[ET.Element, _Doc]] = {}
        # Conventional prefix per namespace, taken from the XSDs' own
        # declarations: used only when JSON->XML must invent a prefix.
        self.prefixes: dict[str, str] = {}
        self._models: dict[int, ContentModel] = {}
        self._anon_docs: dict[int, _Doc] = {}
        for f in files:
            self._load(Path(f))
        self.namespaces = {q.split("}", 1)[0][1:] for q in self.elements}

    # -- loading -----------------------------------------------------------

    def _load(self, path: Path) -> None:
        prefixes: dict[str, str] = {}
        root = None
        for event, item in ET.iterparse(str(path), events=("start-ns", "start")):
            if event == "start-ns":
                p, uri = item
                prefixes.setdefault(p, uri)
            elif root is None:
                root = item
        assert root is not None and root.tag == _XS + "schema", path
        doc = _Doc(root.get("targetNamespace", ""), prefixes,
                   root.get("elementFormDefault") == "qualified")
        for p, uri in prefixes.items():
            if p and uri not in (XS,):
                self.prefixes.setdefault(uri, p)
        for node in root:
            name = node.get("name")
            if not name:
                continue
            q = f"{{{doc.target}}}{name}"
            if node.tag == _XS + "element":
                self.elements.setdefault(q, (node, doc))
            elif node.tag in (_XS + "complexType", _XS + "simpleType"):
                self.types.setdefault(q, (node, doc))
            elif node.tag == _XS + "group":
                self.groups.setdefault(q, (node, doc))

    @staticmethod
    def _resolve(value: str, doc: _Doc) -> str:
        # A QName-valued attribute resolves through the XSD's own prefix
        # declarations; an unprefixed one through its default namespace, and
        # to no namespace when there is none (XML Schema 1.0, 3.15.3).
        prefix, _, local = value.rpartition(":")
        if prefix not in doc.prefixes and prefix:
            raise ValueError(f"undeclared prefix {prefix!r} in schema QName {value!r}")
        return "{{{}}}{}".format(doc.prefixes.get(prefix, ""), local)

    # -- queries -----------------------------------------------------------

    def element_type(self, qname: str) -> TypeRef:
        """The type of a GLOBAL element, or None when it is not declared."""
        hit = self.elements.get(qname)
        if hit is None:
            return None
        node, doc = hit
        return self._decl_type(node, doc)

    def has_element(self, qname: str) -> bool:
        return qname in self.elements

    def has_type(self, qname: str) -> bool:
        return qname in self.types

    def _decl_type(self, node: ET.Element, doc: _Doc) -> TypeRef:
        t = node.get("type")
        if t:
            q = self._resolve(t, doc)
            return None if q.startswith(f"{{{XS}}}") else q
        anon = node.find(_XS + "complexType")
        if anon is not None:
            self._anon_docs[id(anon)] = doc
            return anon
        return None

    def content(self, ref: TypeRef) -> ContentModel:
        """The content model of a type (cached)."""
        if ref is None:
            return ContentModel(simple=True)
        if isinstance(ref, str):
            hit = self.types.get(ref)
            if hit is None:
                return ContentModel(simple=True)
            node, doc = hit
        else:
            node, doc = ref, self._anon_docs[id(ref)]
        key = id(node)
        if key not in self._models:
            self._models[key] = ContentModel()   # recursion guard
            self._models[key] = self._build(node, doc)
        return self._models[key]

    def _build(self, node: ET.Element, doc: _Doc) -> ContentModel:
        if node.tag == _XS + "simpleType":
            return ContentModel(simple=True)
        model = ContentModel()
        counter = [0]
        for child in node:
            tag = child.tag
            if tag == _XS + "simpleContent":
                model.simple = True
            elif tag == _XS + "complexContent":
                ext = child.find(_XS + "extension")
                res = child.find(_XS + "restriction")
                if ext is not None:
                    base = self.content(self._resolve(ext.get("base", ""), doc))
                    # Base particles come first: an extension appends.
                    for c in sorted(base.children.values(), key=lambda c: c.position):
                        model.children[c.qname] = Child(c.qname, c.max, c.type, counter[0])
                        counter[0] += 1
                    for w in base.wildcards:
                        model.wildcards.append(Wildcard(w.namespaces, w.target, w.max, counter[0]))
                        counter[0] += 1
                    self._particles(ext, doc, 1.0, model, counter)
                elif res is not None:
                    # A restriction restates the whole content model.
                    self._particles(res, doc, 1.0, model, counter)
            else:
                self._particles_one(child, doc, 1.0, model, counter)
        return model

    def _particles(self, node: ET.Element, doc: _Doc, mult: float, model: ContentModel,
                   counter: list[int]) -> None:
        for child in node:
            self._particles_one(child, doc, mult, model, counter)

    def _particles_one(self, child: ET.Element, doc: _Doc, mult: float, model: ContentModel,
                       counter: list[int]) -> None:
        tag = child.tag
        if tag in (_XS + "sequence", _XS + "choice", _XS + "all"):
            # A repeating compositor repeats everything in it: an element with
            # maxOccurs 1 inside a sequence with maxOccurs > 1 is an array.
            self._particles(child, doc, mult * _max(child), model, counter)
        elif tag == _XS + "group":
            ref = child.get("ref")
            if ref:
                hit = self.groups.get(self._resolve(ref, doc))
                if hit is not None:
                    gnode, gdoc = hit
                    self._particles(gnode, gdoc, mult * _max(child), model, counter)
        elif tag == _XS + "element":
            ref = child.get("ref")
            if ref:
                q = self._resolve(ref, doc)
                typ = self.element_type(q)
            else:
                ns = doc.target if (doc.qualified or child.get("form") == "qualified") else ""
                q = "{{{}}}{}".format(ns, child.get("name"))
                typ = self._decl_type(child, doc)
            occurs = mult * _max(child)
            prior = model.children.get(q)
            if prior is None:
                model.children[q] = Child(q, occurs, typ, counter[0])
                counter[0] += 1
            else:
                # The same element twice in one content model: the counts add.
                prior.max += occurs
        elif tag == _XS + "any":
            model.wildcards.append(Wildcard(child.get("namespace", "##any"), doc.target,
                                            mult * _max(child), counter[0]))
            counter[0] += 1
