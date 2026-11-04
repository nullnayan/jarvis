from pathlib import Path

from self_dev import patcher


def _use_fixture_project(monkeypatch, tmp_path):
    (tmp_path / "backend" / "data").mkdir(parents=True)
    monkeypatch.setattr(patcher, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(patcher.file_guard, "PROJECT_ROOT", str(tmp_path))


def test_apply_then_revert_restores_exact_source(monkeypatch, tmp_path):
    _use_fixture_project(monkeypatch, tmp_path)
    target = tmp_path / "backend" / "feature.py"
    target.parent.mkdir(exist_ok=True)
    original = "value = 1\n"
    target.write_text(original, encoding="utf-8")

    ok, reason = patcher.apply_patch({"path": "backend/feature.py", "new_source": "value = 2\n"})
    assert ok, reason
    assert target.read_text(encoding="utf-8") == "value = 2\n"
    ok, reason = patcher.revert_last_self_fix()
    assert ok, reason
    assert target.read_text(encoding="utf-8") == original


def test_apply_rejects_outside_project(monkeypatch, tmp_path):
    _use_fixture_project(monkeypatch, tmp_path)
    ok, reason = patcher.apply_patch({"path": "../outside.py", "new_source": "x = 1\n"})
    assert not ok
    assert "safe" in reason.lower()
