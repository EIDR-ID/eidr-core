# MDDF JSON — how EIDR's Python tools translate XML to JSON and back

**Version:** 1.0.0 — 2026-11-12 (eidr-core 0.70.0, `eidr_core.mddf_json`).
**Source:** MovieLabs *MDDF JSON Encoding Best Practice*, Draft 3 with EIDR's
redline (`BP_JSON_v1.0-DRAFT_RWK-v3`, submitted to MovieLabs 2026-11-11), and
the operator's answers recorded in eidr-core-ops
`MDDF-JSON-BP-ASSESSMENT-2026-11-11.md`.
**Applies to:** every XML↔JSON translation in the Python tools: XML_to_JSON's
standard output (pretty and compact), python-sdk's codec, python-tools
`-f json`. The EIDR API Proxy follows later, with at least a month's notice
to its users.
**Does not apply to:** XML_to_JSON's star JSONL. It is internal, Tamr and the
API Shim read it, and the operator locked it (2026-11-11);
`XML_to_JSON/tests/test_star_lock.py` enforces that.

If MovieLabs changes a rule in review, this spec takes a new version and the
corpus moves with it.

## 1. Rules (XML → JSON)

| # | Rule | Example (corpus case) |
|---|---|---|
| 1 | An element's key is its **local name**, capitalization kept. | `<md:DisplayName>` → `"DisplayName"` (`registry-edit-full`) |
| 2 | An attribute's key is `_` + its name; an attribute in another namespace keeps its prefix. | `lang` → `"_lang"`, `xsi:type` → `"_xsi:type"` (`values-and-empties`) |
| 3 | Namespace declarations are kept as `_xmlns` / `_xmlns:p` on the element that declares them, first in its object. Nothing is added: EIDR XML (a default namespace plus md) is rendered as received. | `registry-edit-full` |
| 4 | An element allowed only by a wildcard (`xs:any`) keeps its prefix as written. | `<ep:Notice>` → `"ep:Notice"` (tests) |
| 5 | All values are **strings**, as written after trimming. | `updateNum="1"` → `"_updateNum": "1"` |
| 6 | Leading/trailing **space, tab, CR and LF** are trimmed from element content and attribute values; nothing else (a no-break space is content). Interior white space is kept. | `values-and-empties` |
| 7 | A value empty after trimming is **null**. An element with no content, or only white space, is null. | `lang=""` → `"_lang": null`; `<ReleaseDate/>` → `null` |
| 8 | An element with attributes and text: the text under `"value"`, then the attributes. With attributes and no text: an object of the attributes only. | `values-and-empties` |
| 9 | `xsi:nil` `"true"` or `"1"` with no other attribute is null; with other attributes, an object of its attributes including `"_xsi:nil"`. | `nil-and-api` |
| 10 | **Arrays by schema, per parent type**: an element whose effective `maxOccurs` in its parent's content model is > 1 (its own times every enclosing repeating compositor) is always an array, even when it occurs once; otherwise a scalar/object. `xsi:type` selects the governing type. | `CountryOfOrigin` (one) → array; `md:DisplayName` in an org name → single (`registry-edit-full`) |
| 11 | Standalone document: one top-level key, the root's local name. API mode: the root is removed; its declarations **and its other attributes** (`xsi:schemaLocation`, `ManifestID`, `updateNum`) stay in the top-level object. Declarations may be omitted only where the API documents the version. | `*.api.json` |
| 12 | **Schema version:** the newest published for the namespace unless the XML names one; a version named by both a versioned namespace and `xsi:schemaLocation` must agree, or the XML is in error. EIDR's namespace is unversioned: the EIDR 2.7.0 set (with EIDR's md 2.8) governs until a newer one is published. | tests |
| 13 | **Signed XML** may be translated only when the signed XML travels with the JSON (embedded per rule 15, or as a separate document). The converter refuses unless the caller says so (`allow_signed=True`). | tests |

Elements the schema does not allow where they occur are keyed by local name
with their cardinality **observed** and a warning (`strict=True` raises). An
element the schema allows once but that occurs twice is an error, never a
silent array. Two children of one element that would share a key (same local
name, different namespaces) is an error.

## 2. Rules (JSON → XML)

| # | Rule |
|---|---|
| 14 | Children are written in **schema order** (the JSON keeps order only among same-named siblings); wildcard and unknown keys after the known ones. A null element is `<X/>`; a null attribute `x=""` (operator, 2026-11-11). `"value"` is the text. Prefixes come from the `_xmlns` keys; API JSON names its root (`root=`) and, if the declarations were omitted, its namespaces (`namespaces=`). `xsi` is declared when used and undeclared. Numbers and booleans (Draft-2-era JSON) are written as their text. |

The reverse reproduces **content, not form**: `<X/>`, `<X> </X>` and
`<X xsi:nil="true"/>` all become `"X": null` and come back as `<X/>`
(EIDR redline E5).

## 3. Embedding (Section 2 of the practice)

`embed_xml(xml)` returns `{"<root element name>": "<the XML, unchanged>"}`:
`CoreMetadata` for a MEC CoreMetadata (operator, 2026-11-11). The text is not
touched, so a signature over it still verifies; JSON escaping (quote,
backslash, control characters) is the serializer's.

## 4. Byte form and the conformance corpus

`dumps(obj, pretty=True)`: `json.dumps(obj, ensure_ascii=False, indent=2)`;
compact: `separators=(",", ":")`. Key order is as built (rules 3, 8, 10).

The corpus ships in the package: `src/eidr_core/specs/mddf_json/`.
`cases.json` lists each case and why it exists; each case has `<id>.xml`,
`<id>.json` (standalone, pretty, trailing newline) and `<id>.api.json`. A
consumer's conformance test translates each `.xml` and compares bytes. Every
case is also a fixed point of XML → JSON → XML → JSON (eidr-core's own
test compares the two directions with each other).

## 5. Known limits

* Mixed content (text between child elements) keeps its characters under
  `"value"` but not their positions; MDDF and EIDR schemas do not use it.
* Interleaved siblings (`A B A B`) cannot be represented; the MDDF and EIDR
  schemas are sequenced, so a repeating group is a complex type and its array
  is of that type (operator, 2026-11-11).
* The schema model reads content models only (not attributes or facets) and
  does not follow `xs:redefine`; the EIDR set ships EIDR's md 2.8 with the
  redefinitions applied (`md-v28-eidr.xsd`).
