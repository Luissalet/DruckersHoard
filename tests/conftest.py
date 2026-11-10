import os
import tempfile

# Set before the app is imported: the copilot router resolves its folder at import time.
os.environ.setdefault("DRUCKER_DATA", tempfile.mkdtemp(prefix="drucker-import-"))

import pytest


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    monkeypatch.setenv("DRUCKER_DATA", str(folder))
    return folder


@pytest.fixture(autouse=True)
def other_hoards_offline(monkeypatch):
    """No test reaches the real family hub: every call to another Hoard answers "hub unreachable" unless the test replaces it."""
    from drucker import links
    monkeypatch.setattr(links, "call", lambda owner, tool, args=None, timeout=10: {"ok": False, "kind": "hub_down", "error": "hub unreachable", "data": None, "status": None})
