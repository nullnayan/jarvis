from self_dev.auditor import parse_audit_findings, static_audit


def test_parse_audit_findings_tolerates_common_model_wrappers():
    expected = [{"severity": "high", "file": "demo.py", "line": 4, "title": "Unbound name"}]
    variants = [
        '[{"severity":"high","file":"demo.py","line":4,"title":"Unbound name"}]',
        'Here are findings:\n```json\n[{"severity":"high","file":"demo.py","line":4,"title":"Unbound name",}]\n```',
        'Result: [{"severity":"high","file":"demo.py","line":4,"title":"Unbound name"}] thanks',
    ]
    for variant in variants:
        assert parse_audit_findings(variant) == expected


def test_static_audit_detects_bare_except_and_syntax_error(tmp_path):
    risky = tmp_path / "risky.py"
    risky.write_text("try:\n    pass\nexcept:\n    pass\n", encoding="utf-8")
    broken = tmp_path / "broken.py"
    broken.write_text("def broken(:\n", encoding="utf-8")
    findings = static_audit([str(risky), str(broken)])
    assert {finding["title"] for finding in findings} >= {"Bare except", "Syntax error"}
