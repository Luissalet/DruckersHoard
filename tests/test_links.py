"""Live references to People, Ledger and Atlas through the family bus, and Atlas pointers in packages."""
import hashlib

import pytest
from fastapi.testclient import TestClient

from drucker import engagements, links, package, review, tools
from drucker.app import app
from helpers import make_files


def ok(data):
    return {"ok": True, "kind": None, "error": None, "data": data, "status": 200}


def down():
    return {"ok": False, "kind": "app_down", "error": "not running", "data": None, "status": None}


class Bus:
    """A stand-in for the family hub: records every call and answers per tool."""

    def __init__(self, monkeypatch, answers):
        self.calls = []
        self.answers = answers
        monkeypatch.setattr(links, "call", self)

    def __call__(self, owner, tool, args=None, timeout=10):
        self.calls.append((owner, tool, args))
        a = self.answers.get((owner, tool))
        return a(args) if callable(a) else (a if a is not None else down())


def _engagement():
    e = engagements.save({"name": "Con referencias", "client_name": "Ana Prueba", "client_ref": {"app": "people", "id": "p-1", "label": "Ana Prueba"}})
    engagements.save_item(e["id"], "payment", {"title": "Anticipo", "kind": "payment", "amount": 500, "date": "2026-10-10", "status": "paid",
                                               "ledger": {"app": "ledger", "id": "L9"}})
    engagements.save_item(e["id"], "material", {"title": "Plano", "kind": "atlas", "ref": "f-77"})
    return e


def test_people_ledger_atlas_are_resolved_without_copying(monkeypatch):
    e = _engagement()
    bus = Bus(monkeypatch, {
        ("people", "get_person"): ok({"person": {"name": "Ana Prueba"}}),
        ("ledger", "list_entries"): ok({"items": [{"id": "L1", "amount_cents": 1}, {"id": "L9", "amount_cents": 50000, "counterparty": "Ana Prueba", "date": "2026-10-11"}]}),
        ("atlas", "atlas_file_resolve"): ok({"file": {"title": "Plano", "path": "C:/x/plano.pdf", "exists": True, "revision": "AB" * 32, "state": "ok"}}),
    })
    before = engagements.get(e["id"])
    r = links.engagement_refs(e["id"])
    by = {i["ref"]["app"]: i["live"] for i in r["items"]}
    assert by["people"]["state"] == "ok" and by["people"]["name"] == "Ana Prueba" and by["people"]["matches_stored"] is True
    assert by["ledger"]["amount"] == 500.0 and by["ledger"]["matches_stored"] is True and by["ledger"]["date"] == "2026-10-11"
    assert by["atlas"]["path"] == "C:/x/plano.pdf" and by["atlas"]["sha256"] == "ab" * 32 and by["atlas"]["exists"] is True
    assert r["counts"] == {"ok": 3}
    assert any(c[1] == "get_person" and c[2] == {"person": "p-1"} for c in bus.calls)
    assert engagements.get(e["id"]) == before  # nothing was stored


def test_a_name_or_amount_that_changed_is_reported(monkeypatch):
    e = _engagement()
    Bus(monkeypatch, {("people", "get_person"): ok({"person": {"name": "Beatriz Otra"}}),
                      ("ledger", "list_entries"): ok({"items": [{"id": "L9", "amount_cents": 45000, "date": "2026-10-10"}]})})
    by = {i["ref"]["app"]: i["live"] for i in links.engagement_refs(e["id"])["items"]}
    assert by["people"]["matches_stored"] is False and by["ledger"]["matches_stored"] is False
    assert by["atlas"]["state"] == "unavailable"


def test_apps_down_and_unknown_entries_are_told_apart(monkeypatch):
    e = _engagement()
    r = links.engagement_refs(e["id"])  # autouse fixture: hub unreachable
    assert {i["live"]["state"] for i in r["items"]} == {"unavailable"}
    Bus(monkeypatch, {("ledger", "list_entries"): ok({"items": []}), ("ledger", "search_entries"): ok({"items": []}),
                      ("people", "get_person"): {"ok": False, "kind": "tool_error", "error": "no person", "data": None, "status": 404}})
    by = {i["ref"]["app"]: i["live"]["state"] for i in links.engagement_refs(e["id"])["items"]}
    assert by["ledger"] == "not_found" and by["people"] == "not_found"


def test_pointer_forms_and_unsupported_apps():
    assert links.ident("hoard://atlas/file/abc") == "abc" and links.ident("atlas:xyz") == "xyz" and links.ident(" 5 ") == "5"
    assert links.atlas_id({"atlas": {"app": "atlas", "id": "q"}}) == "q"
    assert links.resolve({"app": "calendar", "id": "1"})["state"] == "unsupported"


def test_tool_and_route(monkeypatch):
    e = _engagement()
    Bus(monkeypatch, {("people", "get_person"): ok({"person": {"name": "Ana Prueba"}})})
    out = tools.HANDLERS["drucker_refs_resolve"]({"engagement_id": e["id"]})
    assert out["counts"]["ok"] == 1
    r = TestClient(app).get(f"/api/engagements/{e['id']}/refs", headers={"X-Lang": "en"})
    assert r.status_code == 200 and r.json()["items"]
    assert TestClient(app).get("/api/engagements/nope/refs").status_code == 404


# ---- Atlas pointers inside a package
@pytest.fixture
def pk(tmp_path):
    files = make_files(tmp_path)
    e = engagements.save({"name": "Paquete Atlas"})
    d = review.save_deliverable(e["id"], "Informe", "pdf")
    d = review.add_version(d["id"], files["source.json"])
    spec = {"editable_files": [files["source.json"]], "exports": [], "data_sources": [{"name": "ventas.csv", "authorised": True}],
            "instructions": "Abrir y exportar.", "limitations": ["Solo ejemplo"]}
    return d, files, spec


def _atlas(path, sha, exists=True):
    return ok({"file": {"title": "Informe", "path": path, "exists": exists, "revision": sha, "state": "ok" if exists else "missing"}})


def test_atlas_pointer_resolves_to_the_live_path_and_hash(monkeypatch, pk):
    d, files, spec = pk
    sha = hashlib.sha256(open(files["report.pdf"], "rb").read()).hexdigest()
    Bus(monkeypatch, {("atlas", "atlas_file_resolve"): _atlas(files["report.pdf"], sha)})
    spec["exports"] = ["atlas:f-1"]
    r = package.build(d["id"], 1, spec)
    assert r["ready"] is True, r["failed"]
    assert any(c["id"] == "atlas:export:f-1" and c["ok"] for c in r["checks"])


def test_atlas_revision_that_does_not_match_the_bytes_fails(monkeypatch, pk):
    d, files, spec = pk
    Bus(monkeypatch, {("atlas", "atlas_file_resolve"): _atlas(files["report.pdf"], "0" * 64)})
    spec["exports"] = ["atlas:f-1"]
    r = package.verify_only(d["id"], 1, spec)
    assert r["ready"] is False and any(c["id"].startswith("atlas_rev:") for c in r["failed"])


def test_atlas_missing_file_or_app_down_fails_but_recorded_path_is_a_fallback(monkeypatch, pk):
    d, files, spec = pk
    Bus(monkeypatch, {("atlas", "atlas_file_resolve"): _atlas("", None, exists=False)})
    spec["exports"] = ["atlas:f-1"]
    assert package.verify_only(d["id"], 1, spec)["ready"] is False
    Bus(monkeypatch, {})  # the hub is unreachable
    spec["exports"] = ["atlas:f-1"]
    assert package.verify_only(d["id"], 1, spec)["ready"] is False  # hub down, nothing recorded
    spec["exports"] = [{"atlas": "f-1", "path": files["report.pdf"]}]
    r = package.verify_only(d["id"], 1, spec)
    assert r["ready"] is True and any(c["id"] == "atlas:export:f-1" for c in r["checks"])
