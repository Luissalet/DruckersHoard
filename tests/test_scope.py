import pytest

from drucker import scope
from drucker.errors import DruckerError

AGREEMENT = [
    "Informe mensual de ventas en PDF generado desde el CSV de ventas",
    "Panel con tres gráficos de ingresos",
    "Formación de 2 horas para el equipo",
    "Entrega de 5 plantillas de correo",
]
CONTEXT = {"deliverables": ["Informe mensual de ventas", "Panel"],
           "milestones": [{"title": "Informe v1", "status": "in_progress"}, {"title": "Panel de ingresos", "status": "planned"}]}


def by_text(result, fragment):
    return next(i for i in result["items"] if fragment in i["text"])


def run(request, **kw):
    return scope.compare(initial=AGREEMENT, agreement=AGREEMENT, request=request, context=CONTEXT, **kw)


def test_format_change_and_pipeline_rework_get_different_ranges_with_reasons():
    r = run(["Queremos el informe mensual de ventas también en DOCX",
             "Generar el informe automáticamente conectando con la base de datos de pedidos"])
    fmt = by_text(r, "DOCX")["effort"]
    pipe = by_text(r, "base de datos")["effort"]
    assert fmt["kind"] == "format" and pipe["kind"] == "pipeline"
    assert fmt["hours"]["max"] <= 4 and pipe["hours"]["min"] >= 16
    assert pipe["hours"]["min"] > fmt["hours"]["max"]
    assert "last stage" in fmt["reason"] and "earlier stage" in pipe["reason"]
    assert "Informe mensual de ventas" in fmt["touches"]["deliverables"]
    assert "Informe mensual de ventas" in pipe["reason"]


def test_pipeline_range_grows_with_touched_deliverables_and_open_milestones():
    one = scope.compare(agreement=AGREEMENT, request=["Integrar la base de datos de pedidos"], context={"deliverables": [], "milestones": []})
    many = scope.compare(agreement=AGREEMENT, request=["Integrar la base de datos de pedidos en el informe mensual de ventas y el panel de ingresos"], context=CONTEXT)
    a = one["items"][0]["effort"]["hours"]
    assert many["items"][0]["effort"]["hours"]["max"] > a["max"]


def test_classes_on_fixture():
    r = run(["Informe mensual de ventas en PDF generado desde el CSV de ventas",
             "Formación para el equipo", "Entrega de 8 plantillas de correo", "Una app móvil para comerciales"])
    cls = {i["text"][:12]: i["class"] for i in r["items"]}
    assert cls["Informe mens"] == "unchanged"
    assert cls["Formación pa"] == "already_included"
    assert cls["Entrega de 8"] == "ambiguous"
    assert cls["Una app móvi"] == "added"
    assert r["counts"]["unchanged"] == r["counts"]["already_included"] == r["counts"]["ambiguous"] == r["counts"]["added"] == 1


def test_quantity_change_is_ambiguous_with_a_unit_range():
    item = by_text(run(["Entrega de 8 plantillas de correo"]), "8 plantillas")
    assert item["class"] == "ambiguous" and "5 -> 8" in item["reason"]
    assert item["effort"]["kind"] == "quantity" and item["effort"]["hours"] == {"min": 0.0, "max": 9.0}


def test_negation_flip_is_ambiguous():
    r = scope.compare(agreement=["Entrega del informe con anexos"], request=["Entrega del informe sin anexos"])
    assert r["items"][0]["class"] == "ambiguous" and "negation" in r["items"][0]["reason"]


def test_removed_only_in_full_mode():
    delta = scope.compare(agreement=AGREEMENT, request=["Panel con tres gráficos de ingresos"], request_mode="delta")
    full = scope.compare(agreement=AGREEMENT, request=["Panel con tres gráficos de ingresos"], request_mode="full")
    assert delta["removed"] == [] and len(full["removed"]) == 3 and full["counts"]["removed"] == 3
    assert full["removed"][0]["effort"]["direction"] == "save"


def test_text_input_with_bullets_and_structured_items_with_touches():
    r = scope.compare(agreement="- Informe en PDF\n- Panel de ingresos", request=[{"id": "x1", "text": "Informe en DOCX", "touches": {"deliverables": ["Informe", "Resumen"]}}])
    assert r["items"][0]["effort"]["touches"]["deliverables"] == ["Informe", "Resumen"]
    assert r["items"][0]["id"] == "x1"


def test_money_only_with_a_rate_range_and_never_a_single_price():
    plain = run(["Generar el informe automáticamente conectando con la base de datos de pedidos"])
    assert "money" not in plain["items"][0]["effort"]
    priced = run(["Generar el informe automáticamente conectando con la base de datos de pedidos"], hourly_rate={"min": 50, "max": 70, "currency": "EUR"})
    m = priced["items"][0]["effort"]["money"]
    assert m["min"] < m["max"] and m["currency"] == "EUR"
    with pytest.raises(DruckerError):
        run(["x"], hourly_rate={"min": 90, "max": 10})


def test_three_commercial_options_and_a_recommendation():
    small = by_text(run(["Queremos el informe mensual de ventas en DOCX"]), "DOCX")
    big = by_text(run(["Automatizar con la base de datos de pedidos"]), "base de datos")
    assert [a["option"] for a in big["alternatives"]] == ["include", "change_order", "defer"]
    assert big["recommended"] == "change_order"
    assert small["recommended"] in ("clarify", "include")


def test_dropped_from_agreement_is_noted():
    r = scope.compare(initial=["Integración con el almacén"], agreement=["Informe mensual"], request=["Integración con el almacén"])
    assert "initial request" in r["items"][0].get("note", "")


def test_inputs_are_validated():
    with pytest.raises(DruckerError):
        scope.compare(agreement=AGREEMENT, request="")
    with pytest.raises(DruckerError):
        scope.compare(request=["a b c"])
    with pytest.raises(DruckerError):
        scope.compare(agreement=AGREEMENT, request=["x y"], request_mode="other")
