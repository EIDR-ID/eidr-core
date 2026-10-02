"""load_local's comma repair must never change a value, and BOM files must load.

Both failures were silent or confusing: the old regex rewrote ',}' inside a
string (a password containing it was altered with no error), and a file saved
with a byte-order mark was refused as invalid JSON (dictionary audit,
2026-10-02).
"""
import json

import pytest

from eidr_core.secrets_loader import SecretsError, _strip_trailing_commas, load_local


def _write(tmp_path, text, encoding="utf-8"):
    p = tmp_path / ".secrets.json"
    p.write_text(text, encoding=encoding)
    return p


def test_trailing_commas_are_tolerated(tmp_path):
    p = _write(tmp_path, '{"registry": {"USER_ID": "u", "PASSWORD": "p",},}')
    assert load_local(p) == {"registry": {"USER_ID": "u", "PASSWORD": "p"}}


def test_a_comma_inside_a_string_is_never_touched(tmp_path):
    p = _write(tmp_path, '{"pw": "x,}", "list": ["a,]", "b",],}')
    assert load_local(p) == {"pw": "x,}", "list": ["a,]", "b"]}


def test_escaped_quotes_do_not_end_a_string():
    text = '{"pw": "q\\",}x", "k": 1,}'
    assert json.loads(_strip_trailing_commas(text)) == {"pw": 'q",}x', "k": 1}


def test_a_byte_order_mark_is_tolerated(tmp_path):
    p = _write(tmp_path, '{"a": 1}', encoding="utf-8-sig")
    assert load_local(p) == {"a": 1}


def test_valid_json_is_returned_as_parsed(tmp_path):
    p = _write(tmp_path, '{"a": ",}"}')
    assert load_local(p) == {"a": ",}"}


def test_broken_json_still_raises_secrets_error(tmp_path):
    p = _write(tmp_path, '{"a": }')
    with pytest.raises(SecretsError):
        load_local(p)
