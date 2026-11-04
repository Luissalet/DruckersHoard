"""Effort bands saved as a setting: every scope comparison uses them unless the call passes its own."""
import pytest
from fastapi.testclient import TestClient

from drucker import engagements, examples, scope, tools
from drucker.app import app
from drucker.errors import DruckerError


def _compare(**extra):
    return tools.HANDLERS["drucker_scope_compare"]({**examples.example_scope(), **extra})


def _doubled():
    return {fam: {part: [lo * 2, hi * 2] for part, (lo, hi) in parts.items()} for fam, parts in scope.DEFAULT_BANDS.items()}


def test_defaults_until_the_owner_saves_bands():
    st = engagements.get_settings()
    assert st["bands"] == st["default_bands"] and st["bands_custom"] == {}
    assert _compare()["bands"] == scope.merge_bands()


def test_saved_bands_drive_every_comparison_and_reset_restores_defaults():
    base = _compare()
    assert base["totals"]["hours"]["max"] > 0
    engagements.set_settings({"bands": _doubled()})
    wide = _compare()
    assert wide["bands"]["pipeline"]["base"] == [32, 80]
    assert wide["totals"]["hours"]["max"] > base["totals"]["hours"]["max"]
    # a call's own bands still win over the saved ones, part by part
    own = _compare(bands={"pipeline": {"base": [1, 1]}})
    assert own["bands"]["pipeline"]["base"] == [1, 1] and own["bands"]["format"]["per_deliverable"] == [2, 8]
    engagements.set_settings({"bands": {}})
    assert _compare()["totals"] == base["totals"]


def test_partial_update_merges_with_saved_parts_and_keeps_denylist():
    engagements.set_settings({"denylist": ["Zorro"]})
    engagements.set_settings({"bands": {"format": {"per_deliverable": [2, 5]}}})
    st = engagements.set_settings({"bands": {"quantity": {"per_unit": [0.5, 2]}}})
    assert st["bands_custom"] == {"format": {"per_deliverable": [2, 5]}, "quantity": {"per_unit": [0.5, 2]}}
    assert st["bands"]["pipeline"]["base"] == [16, 40] and st["denylist"] == ["Zorro"]


@pytest.mark.parametrize("bad", [{"nope": {"base": [1, 2]}}, {"format": {"base": [1, 2]}}, {"format": {"per_deliverable": [5, 1]}},
                                 {"format": {"per_deliverable": [-1, 1]}}, {"format": {"per_deliverable": [1]}}, ["x"]])
def test_invalid_bands_are_refused(bad):
    with pytest.raises(DruckerError):
        engagements.set_settings({"bands": bad})
    assert engagements.get_settings()["bands_custom"] == {}


def test_rest_and_mcp_tool_read_and_write_bands():
    with TestClient(app) as client:
        assert client.put("/api/settings", json={}).status_code == 422
        assert client.put("/api/settings", json={"bands": {"format": {"per_deliverable": [9, 3]}}}).status_code == 422
        st = client.put("/api/settings", json={"bands": {"format": {"per_deliverable": [2, 6]}}}).json()
        assert st["bands"]["format"]["per_deliverable"] == [2, 6]
        assert client.get("/api/settings").json()["bands_custom"] == {"format": {"per_deliverable": [2, 6]}}
    read = tools.HANDLERS["drucker_settings"]({})
    assert read["bands"]["format"]["per_deliverable"] == [2, 6]
    reset = tools.HANDLERS["drucker_settings"]({"bands": {}})
    assert reset["bands_custom"] == {} and "bands" in next(s for s in tools.SPECS if s[0] == "drucker_settings")[2]


def test_bands_reject_infinite_and_absurd_hours():
    # a JSON 1e999 parses to infinity: it passed the min <= max check and broke the save with a server error
    for bad in (float("inf"), float("nan"), 1e308, 100001):
        with pytest.raises(DruckerError):
            scope.validate_bands({"pipeline": {"base": [1, bad]}})
    assert scope.validate_bands({"pipeline": {"base": [0, 100000]}}) == {"pipeline": {"base": [0, 100000]}}
