from security.file_guard import is_restricted_file, is_writable_source


def test_sensitive_and_guardrail_files_are_not_writable():
    assert is_restricted_file("security/vault.py")
    assert not is_writable_source("security/vault.py")
    assert not is_writable_source("config.py")


def test_normal_source_is_writable_and_traversal_is_rejected():
    from security.file_guard import PROJECT_ROOT
    import os

    assert is_writable_source(os.path.join(PROJECT_ROOT, "backend", "pipeline.py"))
    assert not is_writable_source(os.path.join(PROJECT_ROOT, "..", "outside.py"))
