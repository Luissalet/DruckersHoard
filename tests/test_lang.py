"""Every text the server produces for people follows `lang`; machine fields stay the same in both languages."""
import re

import pytest
from fastapi.testclient import TestClient

from drucker import engagements, examples, package, proposal, review, scope, tools
from drucker.app import app, token
from helpers import make_files

AGREEMENT = ["Informe mensual de ventas en PDF generado desde el CSV de ventas", "Panel con tres gráficos de ingresos",
             "Formación de 2 horas para el equipo", "Entrega de 5 plantillas de correo"]
REQUEST = ["Queremos el informe mensual de ventas también en DOCX", "Generar el informe automáticamente conectando con la base de datos de pedidos",
           "Entrega de 8 plantillas de correo", "Formación para el equipo", "Una app móvil para comerciales"]


def texts_of(r):
    out = [r["method"]]
    for i in r["items"]:
        out += [i["reason"], i["effort"]["reason"], i.get("note", "")]
        for a in i.get("alternatives", []):
            out += [a["label"], a["summary"]]
    return " ".join(out)


def test_scope_texts_are_spanish_with_lang_es_and_english_with_lang_en():
    es = scope.compare(agreement=AGREEMENT, request=REQUEST, lang="es")
    en = scope.compare(agreement=AGREEMENT, request=REQUEST, lang="en")
    t_es, t_en = texts_of(es), texts_of(en)
    for phrase in ("Se solapa con un punto acordado", "Cambio de formato de salida", "Asumir", "Similitud determinista"):
        assert phrase in t_es
    for phrase in ("Overlaps an agreed item", "Output format change", "Absorb", "Deterministic token"):
        assert phrase in t_en
    assert not re.search(r"Overlaps|Output format|Absorb|Deterministic|Change order", t_es)
    assert not re.search(r"Se solapa|Cambio de formato|Asumir|Similitud|Orden de cambio", t_en)
    # machine fields are language-neutral
    strip = lambda r: [(i["id"], i["class"], i["effort"]["kind"], i["effort"]["hours"], i.get("recommended"),
                        [a["option"] for a in i.get("alternatives", [])]) for i in r["items"]]
    assert strip(es) == strip(en) and es["counts"] == en["counts"] and es["totals"] == en["totals"]
    assert es["lang"] == "es" and en["lang"] == "en"


def test_unmatched_new_item_has_no_hours_and_is_left_out_of_the_totals():
    r = scope.compare(agreement=AGREEMENT, request=["Una app móvil para comerciales"], lang="es")
    item = r["items"][0]
    assert item["class"] == "added" and item["estimated"] is False
    assert item["effort"]["kind"] == "unestimated" and item["effort"]["hours"] is None and "money" not in item["effort"]
    assert [a["option"] for a in item["alternatives"]] == ["specify", "defer"] and item["recommended"] == "specify"
    assert r["totals"]["hours"] == {"min": 0.0, "max": 0.0} and r["totals"]["unestimated_items"] == 1
    assert "Sin estimar" in item["effort"]["reason"]
    # with a rate there is still no money for it
    priced = scope.compare(agreement=AGREEMENT, request=["Una app móvil para comerciales"], hourly_rate={"min": 50, "max": 70, "currency": "EUR"})
    assert "money" not in priced["items"][0]["effort"]


def test_totals_only_add_the_estimated_items_and_count_the_rest():
    r = scope.compare(agreement=AGREEMENT, request=["Queremos el informe mensual de ventas en DOCX", "Una app móvil para comerciales", "Un portal de clientes"])
    docx = next(i for i in r["items"] if "DOCX" in i["text"])
    assert docx["effort"]["kind"] == "format"
    assert r["totals"]["hours"]["max"] == docx["effort"]["hours"]["max"] and r["totals"]["unestimated_items"] == 2


def test_explicit_hours_are_used_as_given_and_validated():
    r = scope.compare(agreement=AGREEMENT, request=[{"text": "Una app móvil para comerciales", "hours": {"min": 80, "max": 120}}], lang="en")
    e = r["items"][0]["effort"]
    assert e["kind"] == "given" and e["hours"] == {"min": 80, "max": 120} and r["totals"]["hours"]["max"] == 120
    assert r["items"][0]["estimated"] is True and "Hours given by you" in e["reason"]
    with pytest.raises(Exception):
        scope.compare(agreement=AGREEMENT, request=[{"text": "algo", "hours": [9, 1]}])


def test_proposal_texts_follow_lang():
    e = examples.load_example()
    es, en = proposal.build(e["id"], lang="es"), proposal.build(e["id"], lang="en")
    assert es["legend"].startswith("Borrador") and en["legend"].startswith("Draft")
    assert es["sections"]["scope"] == "Alcance" and en["sections"]["scope"] == "Scope"
    bare = engagements.save({"name": "Vacío"})
    assert any("¿Quién es el contacto" in s["text"] for s in proposal.build(bare["id"], lang="es")["sentences"])
    assert any("Who is the client contact" in s["text"] for s in proposal.build(bare["id"], lang="en")["sentences"])


def test_review_desk_and_history_messages_follow_lang(tmp_path):
    e = engagements.save({"name": "Rev"})
    d = review.save_deliverable(e["id"], "Informe", "pdf")
    for body in (b"uno", b"dos"):
        p = tmp_path / f"{body.decode()}.bin"
        p.write_bytes(body)
        d = review.add_version(d["id"], str(p))
    d = review.add_comment(d["versions"][0]["id"], "Mal título")
    es, en = review.desk(d["id"], lang="es"), review.desk(d["id"], lang="en")
    assert "es más nueva y distinta" in es["comments"][0]["note"] and "is newer and differs" in en["comments"][0]["note"]
    assert es["warnings"] == ["No hay versión elegida para entregar."] and en["warnings"] == ["No version selected to deliver."]
    assert es["comments"][0]["stale"] is True and en["comments"][0]["stale"] is True
    h_es = [h["summary"] for h in engagements.history(e["id"], lang="es")]
    h_en = [h["summary"] for h in engagements.history(e["id"], lang="en")]
    assert "Informe v1: comentario añadido" in h_es and "Informe: versión 2 añadida" in h_es and "Encargo creado: Rev" in h_es
    assert "Informe v1: comment added" in h_en and "Informe: version 2 added" in h_en and "Engagement created: Rev" in h_en


def test_history_kind_names_are_translated():
    e = engagements.save({"name": "K", "items": {"scope": [{"title": "Informe"}]}})
    assert any(h["summary"] == "alcance: añadido «Informe»" for h in engagements.history(e["id"], lang="es"))
    assert any(h["summary"] == "scope added: Informe" for h in engagements.history(e["id"], lang="en"))


def test_package_checks_and_errors_follow_lang(tmp_path):
    files = make_files(tmp_path)
    e = engagements.save({"name": "Pk"})
    d = review.save_deliverable(e["id"], "Modelo", "glb")
    d = review.add_version(d["id"], files["source.json"])
    bad = package.verify_only(d["id"], 1, {"editable_files": [files["source.json"]], "exports": [str(tmp_path / "falta.pdf")]}, lang="es")
    en = package.verify_only(d["id"], 1, {"editable_files": [files["source.json"]], "exports": [str(tmp_path / "falta.pdf")]}, lang="en")
    by = lambda r: {c["id"]: c for c in r["checks"]}
    assert by(bad)["instructions"]["label"] == "Instrucciones presentes" and by(en)["instructions"]["label"] == "Instructions present"
    miss = [c for c in bad["checks"] if c["id"].startswith("file:export")][0]
    assert miss["detail"] == "No se encuentra el archivo." and miss["label"].startswith("exportación:")
    assert [c for c in en["checks"] if c["id"].startswith("file:export")][0]["detail"] == "File not found."
    assert set(by(bad)) == set(by(en))                      # check ids are the same in both languages
    with pytest.raises(Exception, match="No existe el entregable"):
        package.verify_only("nope", 1, {}, lang="es")


def test_tool_and_http_accept_lang_and_errors_are_translated():
    es = tools.call("drucker_scope_compare", {"agreement": AGREEMENT, "request": "Una app móvil para comerciales", "lang": "es"})
    en = tools.call("drucker_scope_compare", {"agreement": AGREEMENT, "request": "Una app móvil para comerciales", "lang": "en"})
    assert "Sin estimar" in es["items"][0]["effort"]["reason"] and "Not estimated" in en["items"][0]["effort"]["reason"]
    with pytest.raises(Exception, match="No existe el encargo"):
        tools.call("drucker_engagement_get", {"engagement_id": "nope", "lang": "es"})
    with pytest.raises(Exception, match="lang"):
        tools.call("drucker_engagements", {"lang": "fr"})
    with TestClient(app) as c:
        r = c.post("/api/scope/compare", json={"agreement": "\n".join(AGREEMENT), "request": "Una app móvil para comerciales", "lang": "es"})
        assert r.status_code == 200 and "Sin estimar" in r.json()["items"][0]["effort"]["reason"]
        r = c.post("/api/scope/compare", headers={"X-Lang": "es"}, json={"agreement": "\n".join(AGREEMENT), "request": "Una app móvil para comerciales"})
        assert "Sin estimar" in r.json()["items"][0]["effort"]["reason"]
        r = c.post("/api/scope/compare", json={"agreement": "\n".join(AGREEMENT), "request": "Una app móvil para comerciales"})
        assert "Not estimated" in r.json()["items"][0]["effort"]["reason"]
        assert c.get("/api/engagements/nope", headers={"X-Lang": "es"}).json()["error"] == "No existe el encargo 'nope'"
        assert c.get("/api/engagements/nope", headers={"X-Lang": "en"}).json()["error"] == "Engagement 'nope' not found"
        r = c.post("/api/agent/call", headers={"Authorization": "Bearer " + token()}, json={"name": "drucker_engagement_get", "arguments": {"engagement_id": "nope", "lang": "es"}})
        assert r.status_code == 404 and r.json()["error"] == "No existe el encargo 'nope'"
        e = examples.load_example()
        h = c.get(f"/api/engagements/{e['id']}/history", headers={"X-Lang": "es"}).json()
        assert any("Encargo creado" in x["summary"] for x in h)
        assert any("Encargo creado" not in x["summary"] and x["summary"] for x in h)
