"""Commercial decisions, change-order report, proposal templates and DOCX, and synonyms per engagement."""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from drucker import decisions, engagements, formats, proposal, scope, templates, tools
from drucker.app import app
from drucker.errors import DruckerError


def _eng(**kw):
    return engagements.save({"name": "Cliente prueba", "client_name": "Ana", "status": "active", **kw})


# ---- decisions
def test_change_order_is_logged_with_range_and_becomes_an_agreed_scope_item():
    e = _eng()
    out = decisions.decide(e["id"], "Exportar también a PDF", "change_order", hours={"min": 4, "max": 8},
                           money={"min": 200, "max": 400, "currency": "eur"}, why="Lo pidió el cliente", who="Luis", date="2026-11-02")
    d = out["decision"]
    assert d["option"] == "change_order" and d["hours"] == {"min": 4, "max": 8} and d["money"]["currency"] == "EUR" and d["date"] == "2026-11-02"
    assert out["scope_item"]["origin"] == "change" and out["scope_item"]["status"] == "agreed"
    got = engagements.get(e["id"])
    assert [i["title"] for i in got["items"]["scope"]] == ["Exportar también a PDF"] and len(got["items"]["decision"]) == 1
    assert any(h["entity"] == "decision" for h in engagements.history(e["id"]))


def test_defer_and_specify_add_nothing_to_the_scope_and_need_no_hours():
    e = _eng()
    decisions.decide(e["id"], "Panel nuevo", "defer", why="Fase 2")
    decisions.decide(e["id"], "Integración X", "specify")
    got = engagements.get(e["id"])
    assert got["items"]["scope"] == [] and len(got["items"]["decision"]) == 2


def test_rules():
    e = _eng()
    with pytest.raises(DruckerError):
        decisions.decide(e["id"], "x", "change_order")  # a change order needs its hours
    with pytest.raises(DruckerError):
        decisions.decide(e["id"], "x", "maybe")
    with pytest.raises(DruckerError):
        decisions.decide(e["id"], "  ", "include")
    with pytest.raises(DruckerError):
        decisions.decide("nope", "x", "include")
    with pytest.raises(DruckerError):
        decisions.decide(e["id"], "x", "include", money={"min": 5, "max": 1})
    assert engagements.get(e["id"])["items"]["decision"] == []


def test_include_twice_does_not_duplicate_the_scope_item():
    e = _eng()
    decisions.decide(e["id"], "Subtítulos", "include")
    decisions.decide(e["id"], "Subtítulos", "include")
    assert len(engagements.get(e["id"])["items"]["scope"]) == 1


def test_report_counts_only_the_latest_decision_per_request():
    e = _eng(budget_min=1000, budget_max=2000)
    decisions.decide(e["id"], "Informe mensual", "change_order", hours={"min": 6, "max": 10}, money={"min": 300, "max": 500})
    decisions.decide(e["id"], "Gráficos extra", "change_order", hours={"min": 2, "max": 3})
    decisions.decide(e["id"], "Panel nuevo", "defer")
    decisions.decide(e["id"], "Informe mensual", "defer", why="Cambió de idea")
    r = decisions.change_orders(e["id"])
    assert [x["request"] for x in r["change_orders"]] == ["Gráficos extra"]
    assert r["totals"]["count"] == 1 and r["totals"]["hours"] == {"min": 2, "max": 3} and r["totals"]["money_complete"] is False
    assert {x["request"] for x in r["deferred"]} == {"Panel nuevo", "Informe mensual"} and len(r["superseded"]) == 1
    assert r["budget"]["max"] == 2000


def test_report_markdown_and_totals_by_currency():
    e = _eng()
    decisions.decide(e["id"], "A", "change_order", hours={"min": 1, "max": 2}, money={"min": 10, "max": 20, "currency": "EUR"}, who="Luis")
    decisions.decide(e["id"], "B", "change_order", hours={"min": 3, "max": 4}, money={"min": 5, "max": 6, "currency": "EUR"})
    r = decisions.change_orders(e["id"], "md")
    assert r["totals"]["money"] == {"EUR": {"min": 15.0, "max": 26.0}} and r["totals"]["money_complete"] is True
    assert "**A**" in r["content"] and "15-26 EUR" in r["content"] and "4-6 h" in r["content"]
    with pytest.raises(DruckerError):
        decisions.change_orders(e["id"], "pdf")


def test_empty_report():
    r = decisions.change_orders(_eng()["id"], "md")
    assert r["change_orders"] == [] and r["totals"]["count"] == 0 and r["content"]


def test_decision_routes_tools_and_language():
    e = _eng()
    c = TestClient(app)
    r = c.post(f"/api/engagements/{e['id']}/decide", json={"request": "Mapa 3D", "option": "change_order", "hours": {"min": 5, "max": 9}, "lang": "en"})
    assert r.status_code == 200 and "Mapa 3D" in r.json()["summary"]
    es = c.post(f"/api/engagements/{e['id']}/decide", json={"request": "Mapa 2D", "option": "include", "lang": "es"}).json()["summary"]
    assert es != r.json()["summary"]
    assert c.post(f"/api/engagements/{e['id']}/decide", json={"request": "z", "option": "change_order"}).status_code == 422
    co = c.get(f"/api/engagements/{e['id']}/change-orders").json()
    assert co["totals"]["count"] == 1
    assert "Mapa 3D" in c.get(f"/api/engagements/{e['id']}/change-orders.md").text
    out = tools.HANDLERS["drucker_scope_decide"]({"engagement_id": e["id"], "request": "Otra", "option": "defer"})
    assert out["decision"]["option"] == "defer"
    assert tools.HANDLERS["drucker_change_orders"]({"engagement_id": e["id"], "format": "md"})["content"]


# ---- synonyms
def test_synonyms_validated_and_stored_per_engagement_and_shared():
    e = _eng()
    assert engagements.set_synonyms(e["id"], [["informe", "reporte"]])["groups"] == [["informe", "reporte"]]
    engagements.set_settings({"synonyms": [["panel", "dashboard"]]})
    s = engagements.get_synonyms(e["id"])
    assert s["groups"] == [["informe", "reporte"]] and s["shared"] == [["panel", "dashboard"]] and len(s["in_use"]) == 2
    with pytest.raises(DruckerError):
        engagements.set_synonyms(e["id"], [["solo"]])
    assert engagements.set_synonyms(e["id"], [])["groups"] == []
    engagements.delete(e["id"])


def test_synonym_makes_two_phrasings_match():
    plain = scope.compare(["Informe mensual de ventas"], [], ["Reporte mensual de ventas"], "full") if False else None
    assert plain is None
    base = tools.HANDLERS["drucker_scope_compare"]({"initial": "Informe mensual de ventas", "request": "Reporte mensual de ventas", "request_mode": "full"})
    syn = tools.HANDLERS["drucker_scope_compare"]({"initial": "Informe mensual de ventas", "request": "Reporte mensual de ventas", "request_mode": "full",
                                                   "synonyms": [["informe", "reporte"]]})
    item = syn["items"][0]
    assert item["class"] in ("unchanged", "already_included") and item["match"]["via_synonyms"] is True
    assert base["items"][0]["match"] is None or base["items"][0]["match"]["score"] <= item["match"]["score"]


def test_engagement_synonyms_apply_when_comparing_its_scope():
    e = _eng()
    engagements.save_item(e["id"], "scope", {"title": "Informe mensual de ventas", "status": "agreed", "origin": "initial"})
    engagements.set_synonyms(e["id"], [["informe", "reporte"]])
    r = tools.HANDLERS["drucker_scope_compare"]({"engagement_id": e["id"], "request": "Reporte mensual de ventas", "request_mode": "full"})
    assert r["items"][0]["class"] in ("unchanged", "already_included") and r["synonyms"]


def test_synonym_routes_and_tool():
    e = _eng()
    c = TestClient(app)
    assert c.put(f"/api/engagements/{e['id']}/synonyms", json={"groups": [["a1", "b1"]]}).json()["groups"] == [["a1", "b1"]]
    assert c.get(f"/api/engagements/{e['id']}/synonyms").json()["in_use"] == [["a1", "b1"]]
    assert c.put(f"/api/engagements/{e['id']}/synonyms", json={"groups": "mal"}).status_code == 422
    assert tools.HANDLERS["drucker_synonyms"]({"engagement_id": e["id"]})["groups"] == [["a1", "b1"]]
    assert c.put("/api/settings", json={"synonyms": [["x1", "y1"]]}).json()["synonyms"] == [["x1", "y1"]]


# ---- templates and DOCX
def _full_engagement(kind):
    e = _eng(kind=kind, budget_min=800, budget_max=1200)
    engagements.save_item(e["id"], "scope", {"title": "Informe trimestral", "status": "agreed", "origin": "initial"})
    engagements.save_item(e["id"], "milestone", {"title": "Entrega", "due": "2026-12-01"})
    return e


def test_catalogue_in_both_languages_and_general_adds_nothing():
    es, en = templates.catalogue("es"), templates.catalogue("en")
    assert [t["type"] for t in es] == ["general", "report", "data", "design", "training"] == [t["type"] for t in en]
    assert es[1]["name"] != en[1]["name"]
    base = proposal.build(_full_engagement("general")["id"], "es")
    assert base["template"] == "general"


def test_template_sentences_are_never_presented_as_verified():
    e = _full_engagement("report")
    plain = proposal.build(e["id"], "es", template="general")
    with_t = proposal.build(e["id"], "es")
    assert with_t["template"] == "report" and len(with_t["sentences"]) > len(plain["sentences"])
    known = {s["text"] for s in plain["sentences"]}
    extra = [s for s in with_t["sentences"] if s["text"] not in known]
    assert extra and all(s["tag"] in ("assumption", "question") for s in extra)
    assert proposal.build(e["id"], "en")["sentences"] != with_t["sentences"]
    with pytest.raises(DruckerError):
        proposal.build(e["id"], "es", template="nope")


def test_docx_proposal_is_valid_deterministic_and_refused_with_internal_names(tmp_path):
    e = _full_engagement("data")
    a = proposal.proposal(e["id"], "docx", "es")
    assert a["size"] > 0 and a["sha256"] and a["path"].endswith(".docx")
    ok, detail = formats.validate_format(__import__("pathlib").Path(a["path"]), "docx")
    assert ok is True, detail
    with zipfile.ZipFile(a["path"]) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "Informe trimestral" in xml
    b = proposal.proposal(e["id"], "docx", "es")
    assert b["sha256"] == a["sha256"]
    engagements.set_settings({"denylist": ["Informe"]})
    with pytest.raises(DruckerError):
        proposal.proposal(e["id"], "docx", "es")


def test_template_and_docx_through_the_routes_and_the_tool():
    e = _full_engagement("design")
    c = TestClient(app)
    d = c.post(f"/api/engagements/{e['id']}/proposal", json={"format": "json", "lang": "en", "template": "training"}).json()
    assert d["template"] == "training"
    r = c.get(f"/api/engagements/{e['id']}/proposal.docx?lang=es&template=report")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert zipfile.ZipFile(io.BytesIO(r.content)).testzip() is None
    assert c.get(f"/api/engagements/{e['id']}/proposal.rtf").status_code == 404
    assert [t["type"] for t in c.get("/api/templates", headers={"X-Lang": "en"}).json()["templates"]][0] == "general"
    out = tools.HANDLERS["drucker_proposal"]({"engagement_id": e["id"], "format": "docx", "lang": "es"})
    assert out["path"].endswith(".docx")
    assert tools.HANDLERS["drucker_proposal_templates"]({})["templates"]
    assert c.post("/api/engagements", json={"name": "T", "kind": "data"}).json()["kind"] == "data"
    assert c.post("/api/engagements", json={"name": "T", "kind": "nope"}).status_code == 422


# ---- forms an AI caller tends to send
def test_ranges_may_come_as_a_pair_or_a_number():
    e = _eng()
    engagements.save_item(e["id"], "decision", {"what": "Cambio", "option": "change_order", "hours": [1, 4], "money": [100, 200]})
    engagements.save_item(e["id"], "decision", {"what": "Otro", "option": "change_order", "hours": 3})
    rows = engagements.get(e["id"])["items"]["decision"]
    assert rows[0]["hours"] == {"min": 1.0, "max": 4.0} and rows[0]["money"]["currency"] == "EUR" and rows[1]["hours"] == {"min": 3.0, "max": 3.0}
    with pytest.raises(DruckerError):
        engagements.save_item(e["id"], "decision", {"what": "Mal", "hours": [5, 1]})


def test_a_scope_list_sent_as_json_text_is_still_a_list():
    one = scope.split_items('["Reporte mensual de ventas", "Exportar a PDF"]')
    assert [i["text"] for i in one] == ["Reporte mensual de ventas", "Exportar a PDF"]
    assert [i["text"] for i in scope.split_items("[nota entre corchetes]")] == ["[nota entre corchetes]"]
