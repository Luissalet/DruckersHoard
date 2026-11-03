import pytest

from drucker import engagements
from drucker.errors import DruckerError, NotFound


def make(**kw):
    return engagements.save({"name": "Encargo de prueba", "client_name": "Cliente ficticio", **kw})


def test_create_read_update_and_history():
    e = make(budget_min=1000, budget_max=2000, currency="eur", origin="Referido por un conocido ficticio")
    assert e["currency"] == "EUR" and e["status"] == "lead"
    e2 = engagements.save({"id": e["id"], "status": "active", "budget_max": 2500})
    assert e2["status"] == "active" and e2["budget_max"] == 2500 and e2["name"] == "Encargo de prueba"
    history = engagements.history(e["id"])
    assert [h["action"] for h in history] == ["update", "create"]
    assert history[0]["changes"]["status"] == ["lead", "active"]
    assert history[0]["changes"]["budget_max"] == [2000, 2500]


def test_unchanged_save_writes_no_history():
    e = make()
    engagements.save({"id": e["id"], "name": e["name"]})
    assert len(engagements.history(e["id"])) == 1


def test_budget_range_and_currency_validated():
    with pytest.raises(DruckerError):
        make(budget_min=5, budget_max=1)
    with pytest.raises(DruckerError):
        make(currency="EURO")
    with pytest.raises(DruckerError):
        make(unknown_field=1)


def test_items_every_kind_with_history_and_delete():
    e = make()
    s = engagements.save_item(e["id"], "scope", {"title": "Informe PDF", "status": "agreed", "origin": "agreement"})
    m = engagements.save_item(e["id"], "milestone", {"title": "Primera versión", "due": "2026-12-01"})
    engagements.save_item(e["id"], "material", {"title": "Muestra", "kind": "atlas", "atlas": {"app": "atlas", "id": "f-1"}})
    engagements.save_item(e["id"], "decision", {"what": "PDF", "why": "se imprime", "date": "2026-11-02", "who": "Cliente"})
    engagements.save_item(e["id"], "assumption", {"text": "CSV estable"})
    engagements.save_item(e["id"], "question", {"text": "¿Quién aprueba?"})
    engagements.save_item(e["id"], "scope", {"id": s["id"], "status": "done"})
    got = engagements.get(e["id"])
    assert [i["status"] for i in got["items"]["scope"]] == ["done"]
    assert got["items"]["scope"][0]["title"] == "Informe PDF"
    engagements.delete_item(e["id"], m["id"])
    assert engagements.get(e["id"])["items"]["milestone"] == []
    summaries = [h["summary"] for h in engagements.history(e["id"])]
    assert any("milestone removed" in x for x in summaries) and any("scope updated" in x for x in summaries)
    assert len(summaries) == 1 + 6 + 1 + 1


def test_bad_dates_kinds_and_missing_ids():
    e = make()
    with pytest.raises(DruckerError):
        engagements.save_item(e["id"], "milestone", {"title": "x", "due": "mañana"})
    with pytest.raises(DruckerError):
        engagements.save_item(e["id"], "invoice", {"title": "x"})
    with pytest.raises(NotFound):
        engagements.get("nope")
    with pytest.raises(NotFound):
        engagements.save_item(e["id"], "scope", {"id": "nope", "title": "x"})


def test_payments_without_ledger_ref_are_manual():
    e = make()
    manual = engagements.save_item(e["id"], "payment", {"title": "Anticipo", "amount": 100})
    linked = engagements.save_item(e["id"], "payment", {"title": "Factura 1", "amount": 200, "ledger": {"app": "ledger", "id": "mv-9"}, "source": "manual"})
    assert manual["source"] == "manual" and linked["source"] == "ledger"
    assert linked["ledger"]["id"] == "mv-9"


def test_client_reference_is_a_pointer_only():
    e = make(client_ref={"app": "people", "id": "p-7", "label": "Contacto ficticio"})
    assert e["client_ref"] == {"app": "people", "id": "p-7", "label": "Contacto ficticio"}


def test_nested_items_on_create_and_list_filter():
    e = make(items={"scope": [{"title": "A"}, {"title": "B"}], "milestone": [{"title": "M"}]})
    assert len(e["items"]["scope"]) == 2
    assert [x["id"] for x in engagements.list_engagements(status="lead")] == [e["id"]]
    assert engagements.list_engagements(status="closed") == []
    assert engagements.list_engagements(query="ficticio")[0]["milestones"] == 1


def test_delete_engagement_removes_everything():
    e = make()
    engagements.save_item(e["id"], "scope", {"title": "A"})
    engagements.delete(e["id"])
    with pytest.raises(NotFound):
        engagements.get(e["id"])
