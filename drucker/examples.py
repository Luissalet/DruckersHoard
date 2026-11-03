"""Invented, clearly fictional sample data. No real client, person, price or file."""
from __future__ import annotations

from . import engagements, review

AGREEMENT = [
    "Informe mensual de ventas en PDF generado desde el CSV de ventas",
    "Panel con tres gráficos de ingresos",
    "Formación de 2 horas para el equipo",
    "Entrega de 5 plantillas de correo",
]
REQUEST = """- Queremos el informe mensual de ventas también en DOCX
- Generar el informe automáticamente conectando con la base de datos de pedidos
- Entrega de 8 plantillas de correo
- Formación para el equipo
- Una app móvil para comerciales"""


def example_engagement() -> dict:
    return {
        "name": "Informe mensual de ventas (ejemplo inventado)",
        "client_name": "Cooperativa Ejemplo S. L. (ficticia)",
        "origin": "El cliente ficticio pierde dos días al mes montando un informe de ventas a mano desde hojas CSV.",
        "status": "active", "currency": "EUR", "budget_min": 4000, "budget_max": 6500,
        "notes": "Datos de ejemplo inventados. No corresponden a ningún cliente real.",
        "items": {
            "scope": [{"title": t, "status": "agreed", "origin": "agreement"} for t in AGREEMENT]
                     + [{"title": "App móvil para comerciales", "status": "proposed", "origin": "change"}],
            "milestone": [
                {"title": "Informe v1 con datos de prueba", "due": "2026-12-10", "status": "in_progress"},
                {"title": "Panel de ingresos", "due": "2027-01-14", "status": "planned"},
                {"title": "Formación y cierre", "status": "planned"}],
            "material": [{"title": "CSV de ventas de muestra (inventado)", "kind": "path", "ref": "ejemplo/ventas-demo.csv"},
                         {"title": "Guía de estilo del cliente", "kind": "url", "ref": "https://ejemplo.invalid/guia-estilo"}],
            "decision": [{"what": "El informe se entrega en PDF", "why": "El equipo lo imprime para la reunión semanal", "date": "2026-11-20", "who": "Cliente ficticio"}],
            "payment": [{"title": "Anticipo del 30 %", "kind": "invoice", "amount": 1500, "status": "paid", "date": "2026-11-25"}],
            "assumption": [{"text": "El cliente entrega el CSV con las mismas columnas cada mes"}],
            "question": [{"text": "¿Quién aprueba el diseño del informe por parte del cliente?"}],
        },
    }


def load_example() -> dict:
    e = engagements.save(example_engagement())
    d = review.save_deliverable(e["id"], "Informe mensual de ventas", "pdf")
    review.add_version(d["id"], "ejemplo/informe-v1.pdf", note="Primera versión (ruta inventada)")
    d = review.add_version(d["id"], "ejemplo/informe-v2.pdf", note="Con la corrección del eje de ingresos")
    review.add_comment(d["versions"][0]["id"], "El eje de ingresos empieza en 100, no en 0", "Cliente ficticio", {"kind": "page", "value": 2})
    return engagements.get(e["id"])


def example_scope() -> dict:
    return {"initial": AGREEMENT, "agreement": AGREEMENT, "request": REQUEST, "request_mode": "delta",
            "context": {"deliverables": ["Informe mensual de ventas", "Panel"], "milestones": [{"title": "Informe v1 con datos de prueba", "status": "in_progress"}]}}
