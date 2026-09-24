import re

from uds_assistant.generator.exporters import export_capl, export_csv, export_json, export_python
from uds_assistant.generator.suites import build_suite


def test_export_python_is_valid_python_and_uses_placeholders(profile):
    tests = build_suite(profile)
    src = export_python(profile, tests)
    compile(src, "<generated>", "exec")  # syntax check
    assert "{KEY:" in src or "{BADKEY:" in src


def test_export_json_roundtrips(profile):
    import json
    tests = build_suite(profile)
    data = json.loads(export_json(tests))
    assert len(data) == len(tests)
    assert data[0]["id"] == tests[0].id


def test_export_csv_has_header_and_rows(profile):
    tests = build_suite(profile)
    csv_text = export_csv(tests)
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("TestID,")
    assert len(lines) > len(tests)  # multi-line fields wrap, so at least one row per test


def test_export_capl_has_matching_braces(profile):
    tests = build_suite(profile)[:15]
    files = export_capl(profile, tests)
    can = files["uds_tests.can"]
    assert can.count("{") == can.count("}")
    assert "uds_helpers.cin" in can
    assert re.search(r"testcase TC_", can)
