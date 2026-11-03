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
