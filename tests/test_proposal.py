import pytest

from drucker import engagements, examples, proposal
from drucker.errors import DruckerError


def eng(**kw):
    return engagements.save({"name": "Informe de ventas", "client_name": "Cliente ficticio", "origin": "Montan el informe a mano", **kw})


def test_every_sentence_has_a_tag_and_verified_ones_a_source():
    e = examples.load_example()
    d = proposal.build(e["id"])
    assert d["sentences"] and all(s["tag"] in ("verified", "assumption", "question") for s in d["sentences"])
    assert all(s["source"] for s in d["sentences"] if s["tag"] == "verified")
    assert d["counts"]["verified"] and d["counts"]["assumption"] and d["counts"]["question"]
    tags = {s["text"]: s["tag"] for s in d["sentences"]}
    assert tags["Propuesto, aún no acordado: App móvil para comerciales."] == "assumption"
    assert any(s["tag"] == "question" and "Formación y cierre" in s["text"] for s in d["sentences"])   # milestone without date
    assert any(s["tag"] == "verified" and "4 000 a 6 500 EUR" in s["text"] for s in d["sentences"])


def test_missing_facts_become_questions_not_invented_statements():
    e = engagements.save({"name": "Vacío"})
    d = proposal.build(e["id"], lang="en")
    assert d["counts"]["verified"] == 0 and d["counts"]["question"] >= 4
    assert all(s["source"] is None for s in d["sentences"])


def test_markdown_and_html_export_carry_tags_and_escape():
    e = eng(items={"scope": [{"title": "Informe <b>PDF</b>", "status": "agreed"}]})
    md = proposal.proposal(e["id"], "md", "en")["content"]
    assert md.startswith("# Proposal: Informe de ventas") and "`[verified]`" in md and "## Scope" in md
    html = proposal.proposal(e["id"], "html", "en")["content"]
    assert "&lt;b&gt;PDF&lt;/b&gt;" in html and "<b>PDF</b>" not in html and 'class="t verified"' in html


@pytest.mark.parametrize("fmt", ["md", "html"])
def test_deny_list_refuses_internal_names_in_client_material(fmt):
    e = eng(items={"scope": [{"title": "Exportar desde Faustus y guardar en Atlas", "status": "agreed"}]})
    with pytest.raises(DruckerError) as err:
        proposal.proposal(e["id"], fmt)
    assert "Faustus" in str(err.value) and "Atlas" in str(err.value)
    assert {v["term"] for v in err.value.extra["violations"]} == {"Faustus", "Atlas"}


def test_json_draft_reports_violations_and_is_not_client_ready():
    e = eng(items={"decision": [{"what": "Usar los hoards internos", "why": "ya existen"}]})
    d = proposal.proposal(e["id"], "json")
    assert d["client_ready"] is False and d["violations"][0]["term"] == "Hoard"


def test_deny_list_is_case_and_accent_insensitive_and_catches_titles():
    e = engagements.save({"name": "Migración con FAUSTUS", "client_name": "X"})
    d = proposal.build(e["id"])
    assert [v["sentence_id"] for v in d["violations"]] == ["title"]
    ok = eng(items={"scope": [{"title": "Informe de hoardings y ledgerless", "status": "agreed"}]})
    assert proposal.build(ok["id"])["violations"] == []          # whole words only


def test_deny_list_is_configurable_globally_and_per_engagement():
    e = eng(items={"scope": [{"title": "Usar la herramienta Zorro", "status": "agreed"}]})
    assert proposal.build(e["id"])["violations"] == []
    engagements.set_settings({"denylist": ["zorro"]})
    assert proposal.build(e["id"])["violations"][0]["term"] == "zorro"
    engagements.save({"id": e["id"], "denylist": []})
    assert proposal.build(e["id"])["violations"] == []
    assert proposal.build(e["id"], denylist=["Zorro"])["violations"]


def test_client_name_is_not_scanned():
    e = engagements.save({"name": "Informe", "client_name": "Hoard Farms S. L."})
    assert proposal.build(e["id"])["violations"] == []
