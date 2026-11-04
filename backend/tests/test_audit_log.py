from security import audit_log


def test_audit_log_redacts_sensitive_params(monkeypatch, tmp_path):
    monkeypatch.setattr(audit_log, "AUDIT_DIR", tmp_path)
    audit_log.log_action({"tool": "wifi_control", "params": {"password": "do-not-store", "name": "home"}})
    row = audit_log.read_recent(1)[0]
    assert row["params"]["password"] == "[redacted]"
    assert row["params"]["name"] == "home"


def test_read_recent_preserves_append_order(monkeypatch, tmp_path):
    monkeypatch.setattr(audit_log, "AUDIT_DIR", tmp_path)
    audit_log.log_action({"tool": "first"})
    audit_log.log_action({"tool": "second"})
    assert [entry["tool"] for entry in audit_log.read_recent(2)] == ["first", "second"]
