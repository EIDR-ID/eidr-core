"""eidr_core.mddf_json: the MDDF JSON practice, and its two directions agreeing.

Local tests cover the surfaces whose wrong answer is silent: an array that
should be a scalar (or the reverse) is still valid JSON, and a lost
attribute or a mis-ordered child is still well-formed XML. Consumers'
conformance tests compare byte for byte against the same corpus
(`src/eidr_core/specs/mddf_json/`).
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from eidr_core import mddf_json as m

CORPUS = Path(m.__file__).resolve().parent.parent / "specs" / "mddf_json"
CASES = [c["id"] for c in json.loads((CORPUS / "cases.json").read_text(encoding="utf-8"))["cases"]]


@pytest.mark.parametrize("case", CASES)
def test_corpus_standalone_and_api(case):
    xml = (CORPUS / f"{case}.xml").read_bytes()
    want = (CORPUS / f"{case}.json").read_text(encoding="utf-8")
    assert m.dumps(m.xml_to_json(xml, strict=True)) + "\n" == want
    assert (m.dumps(m.xml_to_json(xml, api=True, strict=True)) + "\n"
            == (CORPUS / f"{case}.api.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES)
def test_the_two_directions_agree(case):
    """XML -> JSON -> XML -> JSON is a fixed point, key order included. A
    per-direction test cannot see the two directions disagree on a name, a
    namespace or the schema order; only the comparison can."""
    first = m.xml_to_json((CORPUS / f"{case}.xml").read_bytes(), strict=True)
    again = m.xml_to_json(m.json_to_xml(first), strict=True)
    assert m.dumps(again) == m.dumps(first)


@pytest.mark.parametrize("case", CASES)
def test_api_json_translates_back_with_root_given(case):
    xml = (CORPUS / f"{case}.xml").read_bytes()
    std = m.xml_to_json(xml, strict=True)
    (local, _), = std.items()
    ns = std[local].get("_xmlns", "")
    back = m.json_to_xml(m.xml_to_json(xml, api=True, strict=True), root=f"{{{ns}}}{local}")
    assert m.dumps(m.xml_to_json(back, strict=True)) == m.dumps(std)


def test_cardinality_is_per_parent_type_not_per_name():
    """`md:DisplayName` is single in an org name and inside Director; `Parent`
    is single in EditInfo. python-sdk's name list made both arrays."""
    j = json.loads((CORPUS / "registry-edit-full.json").read_text(encoding="utf-8"))
    bod = j["FullMetadata"]["BaseObjectData"]
    assert isinstance(bod["AssociatedOrg"][0]["DisplayName"], str)
    assert isinstance(bod["Credits"]["Director"][0]["DisplayName"], str)
    assert isinstance(j["FullMetadata"]["ExtraObjectMetadata"]["EditInfo"]["Parent"], str)
    assert isinstance(bod["CountryOfOrigin"], list)


def test_only_four_characters_are_trimmed():
    nbsp = " "
    xml = ('<SelfDefinedMetadata xmlns="http://www.eidr.org/schema"><BaseObjectData>'
           f'<ResourceName lang="en">{nbsp}Title{nbsp}</ResourceName></BaseObjectData>'
           '</SelfDefinedMetadata>')
    rn = m.xml_to_json(xml)["SelfDefinedMetadata"]["BaseObjectData"]["ResourceName"]
    assert rn["value"] == f"{nbsp}Title{nbsp}"


def test_reverse_writes_null_element_empty_and_null_attribute_empty_string():
    j = {"SelfDefinedMetadata": {"_xmlns": "http://www.eidr.org/schema", "BaseObjectData": {
        "ResourceName": {"value": "Paperman", "_lang": None}, "ReleaseDate": None}}}
    xml = m.json_to_xml(j, xml_declaration=False)
    assert '<ResourceName lang="">Paperman</ResourceName>' in xml
    assert "<ReleaseDate/>" in xml


def test_reverse_uses_schema_order():
    j = {"SelfDefinedMetadata": {"_xmlns": "http://www.eidr.org/schema", "BaseObjectData": {
        "Status": "valid", "ID": "10.5240/0000-0000-0000-0000-0002-X"}}}
    xml = m.json_to_xml(j, xml_declaration=False)
    assert xml.index("<ID>") < xml.index("<Status>")


SIGNED = ('<FullMetadata xmlns="http://www.eidr.org/schema" '
          'xmlns:ds="http://www.w3.org/2000/09/xmldsig#"><BaseObjectData><ID>x</ID></BaseObjectData>'
          '<ds:Signature><ds:SignatureValue>abc</ds:SignatureValue></ds:Signature></FullMetadata>')


def test_signed_xml_needs_the_callers_word_that_it_travels_along():
    assert m.is_signed(SIGNED)
    with pytest.raises(m.SignedXmlError):
        m.xml_to_json(SIGNED)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", m.MddfJsonWarning)
        assert "FullMetadata" in m.xml_to_json(SIGNED, allow_signed=True)


def test_embed_keeps_the_xml_exactly_and_json_escapes_it():
    xml = '<CoreMetadata a="x">\n\tline "q" \\ end</CoreMetadata>'
    e = m.embed_xml(xml)
    assert e == {"CoreMetadata": xml}
    assert json.loads(m.dumps(e, pretty=False)) == e
    assert '\\n\\tline \\"q\\" \\\\ end' in m.dumps(e, pretty=False)


def test_schema_location_disagreeing_with_a_versioned_namespace_is_an_error():
    xml = ('<md:X xmlns:md="http://www.movielabs.com/schema/md/v2.26/md" '
           'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
           'xsi:schemaLocation="http://www.movielabs.com/schema/md/v2.26/md md-v2.8.xsd"/>')
    with pytest.raises(m.MddfJsonError, match="must agree"):
        m.xml_to_json(xml)


# A small schema for the rules the EIDR set has no live instance of.
XSD = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:t="urn:t"
  targetNamespace="urn:t" elementFormDefault="qualified">
  <xs:element name="Root">
    <xs:complexType><xs:sequence>
      <xs:sequence maxOccurs="unbounded">
        <xs:element name="A" type="xs:string"/>
        <xs:element name="B" type="xs:string" minOccurs="0"/>
      </xs:sequence>
      <xs:element name="Single" type="xs:string" minOccurs="0"/>
      <xs:element name="Ext" minOccurs="0"><xs:complexType><xs:sequence>
        <xs:any namespace="##other" minOccurs="0" maxOccurs="unbounded"/>
      </xs:sequence></xs:complexType></xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>"""


@pytest.fixture
def tschema(tmp_path):
    p = tmp_path / "t.xsd"
    p.write_text(XSD, encoding="utf-8")
    return m.SchemaSet([p], label="test")


def test_an_element_in_a_repeating_sequence_is_an_array(tschema):
    j = m.xml_to_json('<Root xmlns="urn:t"><A>1</A></Root>', schema=tschema, strict=True)
    assert j["Root"]["A"] == ["1"]


def test_a_wildcard_element_keeps_its_prefix(tschema):
    xml = ('<Root xmlns="urn:t" xmlns:ep="urn:other"><A>1</A>'
           '<Ext><ep:Notice>n</ep:Notice></Ext></Root>')
    j = m.xml_to_json(xml, schema=tschema, strict=True)
    assert j["Root"]["Ext"] == {"ep:Notice": ["n"]}
    back = m.json_to_xml(j, schema=tschema, xml_declaration=False)
    assert "<ep:Notice>n</ep:Notice>" in back


def test_an_undeclared_element_warns_and_strict_raises(tschema):
    xml = '<Root xmlns="urn:t"><A>1</A><Z>z</Z></Root>'
    with pytest.warns(m.MddfJsonWarning):
        assert m.xml_to_json(xml, schema=tschema)["Root"]["Z"] == "z"
    with pytest.raises(m.MddfJsonError):
        m.xml_to_json(xml, schema=tschema, strict=True)


def test_a_single_element_repeated_is_an_error_not_a_silent_array(tschema):
    with pytest.raises(m.MddfJsonError, match="allows one"):
        m.xml_to_json('<Root xmlns="urn:t"><A>1</A><Single>x</Single><Single>y</Single></Root>',
                      schema=tschema)


def test_api_mode_may_omit_declarations_and_reverse_takes_them_back(tschema):
    j = m.xml_to_json('<Root xmlns="urn:t" id=" 7 "><A>1</A></Root>', schema=tschema, api=True,
                      omit_namespaces=True)
    assert j == {"_id": "7", "A": ["1"]}
    back = m.json_to_xml(j, schema=tschema, root="{urn:t}Root", namespaces={"": "urn:t"},
                         xml_declaration=False)
    assert back == '<Root xmlns="urn:t" id="7"><A>1</A></Root>'
