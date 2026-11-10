"""Effort bands proposed from the real hours of closed engagements."""
import pytest
from fastapi.testclient import TestClient

from drucker import calibration, engagements, tools
from drucker.app import app
from drucker.errors import DruckerError


def _closed(name, hours_list, status="closed", family="format", part="per_deliverable", units=1):
    e = engagements.save({"name": name, "status": status})
    for h in hours_list:
        engagements.save_item(e["id"], "effort", {"title": "Trabajo", "family": family, "part": part, "hours": h, "units": units})
    return e


def test_effort_item_defaults_part_by_family_and_validates():
    e = engagements.save({"name": "Horas"})
    item = engagements.save_item(e["id"], "effort", {"title": "Rehacer", "family": "pipeline", "hours": 12})
    assert item["part"] == "base" and item["units"] == 1
    with pytest.raises(DruckerError):
        engagements.save_item(e["id"], "effort", {"title": "x", "family": "pipeline", "part": "per_unit", "hours": 3})
    with pytest.raises(DruckerError):
        engagements.save_item(e["id"], "effort", {"title": "x", "family": "format", "hours": 0})


def test_three_samples_give_a_proposal_with_dispersion():
    _closed("A", [2, 4, 6])
    r = calibration.suggest()
    row = next(p for p in r["parts"] if p["family"] == "format" and p["part"] == "per_deliverable")
    assert row["n"] == 3 and row["min"] == 2 and row["max"] == 6 and row["mean"] == 4 and row["median"] == 4
    assert row["p10"] < row["mean"] < row["p90"] and row["proposed"] == [row["p10"], row["p90"]]
    assert row["reliability"] == "ok" and row["changes"] is True
    assert r["bands"]["format"]["per_deliverable"] == row["proposed"]


def test_hours_are_per_unit_and_only_closed_engagements_count():
    _closed("Cerrado", [10, 20, 30], family="quantity", part="per_unit", units=10)
    _closed("Activo", [500, 600, 700], status="active", family="quantity", part="per_unit")
    row = next(p for p in calibration.suggest()["parts"] if p["family"] == "quantity")
    assert row["n"] == 3 and row["max"] == 3 and row["min"] == 1
    assert calibration.suggest(status="any")["samples"] == 6


def test_too_few_samples_are_marked_and_never_proposed_for_saving():
    _closed("Uno", [3, 5])
    r = calibration.suggest()
    row = r["parts"][0]
    assert row["reliability"] == "insufficient" and r["bands"] == {}
    assert calibration.suggest(min_samples=2)["bands"]


def test_scattered_hours_are_flagged():
    _closed("Disperso", [1, 1, 1, 40])
    assert calibration.suggest()["parts"][0]["reliability"] == "scattered"


def test_suggest_changes_nothing_and_apply_goes_through_settings():
    _closed("A", [2, 4, 6])
    before = engagements.get_settings()["bands_custom"]
    proposal = calibration.suggest()["bands"]
    assert engagements.get_settings()["bands_custom"] == before == {}
    st = engagements.set_settings({"bands": proposal})
    assert st["bands"]["format"]["per_deliverable"] == proposal["format"]["per_deliverable"]
    assert calibration.suggest()["parts"][0]["changes"] is False


def test_invalid_filters():
    with pytest.raises(DruckerError):
        calibration.suggest(status="whatever")
    with pytest.raises(DruckerError):
        calibration.suggest(min_samples=0)


def test_tool_route_and_language():
    _closed("A", [2, 4, 6])
    out = tools.HANDLERS["drucker_bands_suggest"]({})
    assert out["parts"][0]["n"] == 3
    c = TestClient(app)
    es = c.get("/api/bands/suggest", headers={"X-Lang": "es"}).json()
    en = c.get("/api/bands/suggest", headers={"X-Lang": "en"}).json()
    assert es["parts"][0]["family"] == "format" and es["method"] != en["method"]
    assert c.get("/api/bands/suggest?min_samples=0").status_code in (400, 422)
