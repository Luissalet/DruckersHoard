"""Proposal templates by type of engagement: the standing method, terms and questions that a given kind of work always needs.

The general template adds nothing, so an engagement without a type is drafted exactly as before. Nothing here is a fact about a particular engagement, so every sentence a template adds is tagged ``assumption`` or ``question``
and the owner edits or removes it in the draft. The facts (client, scope, dates, budget) still come from the engagement file."""
from __future__ import annotations

TYPES = ("general", "report", "data", "design", "training")

NAMES = {
    "en": {"general": "General", "report": "Report or analysis", "data": "Data pipeline or automation", "design": "Design or modelling",
           "training": "Training and support"},
    "es": {"general": "General", "report": "Informe o análisis", "data": "Proceso de datos o automatización", "design": "Diseño o modelado",
           "training": "Formación y acompañamiento"},
}

TEMPLATES = {
    "en": {
        "general": {
            "method": [],
            "terms": [],
            "questions": []},
        "report": {
            "method": ["The source data comes from the client in the agreed format, with the same columns every time.",
                       "Each report is built from the sources listed; if a source changes, the client is told before delivery."],
            "terms": ["Two review rounds are included for each delivery.",
                      "A change of output format or of data source is priced separately as a range of hours."],
            "questions": ["How often is the report delivered, and to whom?", "Who checks the figures before they are sent?"]},
        "data": {
            "method": ["The client gives read-only access to the source systems.",
                       "The load is tested first with a sample and then with the full volume."],
            "terms": ["How to rebuild and run the process is documented and delivered with it.",
                      "Changing the data source or the data model counts as a change of scope."],
            "questions": ["Which systems and tables are the source of the data?", "How often must the process run?",
                          "What should happen when a load fails or the data arrives incomplete?"]},
        "design": {
            "method": ["A first visual proposal is shown before the detailed work starts.",
                       "The editable files are delivered together with the final exports."],
            "terms": ["Each extra review round is priced separately.", "Usage rights are agreed in writing before the final delivery."],
            "questions": ["Which final formats does the client need (for example PDF, SVG, GLB, STL)?",
                          "Is there a style guide or reference material to follow?", "How many review rounds are included?"]},
        "training": {
            "method": ["The session is adapted to the team's level, which is confirmed before it starts.",
                       "Supporting material is delivered when the session ends."],
            "terms": ["A session that is postponed is rescheduled by mutual agreement."],
            "questions": ["How many people attend, and what is their starting level?", "Is it in person or remote, and on which dates?",
                          "Is follow-up needed after the session?"]},
    },
    "es": {
        "general": {
            "method": [],
            "terms": [],
            "questions": []},
        "report": {
            "method": ["Los datos de partida los aporta el cliente en el formato acordado y con las mismas columnas cada vez.",
                       "Cada informe se genera a partir de las fuentes indicadas; si una fuente cambia, se avisa al cliente antes de entregar."],
            "terms": ["Se incluyen dos rondas de revisión por entrega.",
                      "Un cambio de formato de salida o de fuente de datos se presupuesta aparte como rango de horas."],
            "questions": ["¿Con qué periodicidad se entrega el informe y a quién?", "¿Quién comprueba las cifras antes de enviarlas?"]},
        "data": {
            "method": ["El cliente da acceso de solo lectura a los sistemas de origen.",
                       "La carga se prueba primero con una muestra y después con el volumen completo."],
            "terms": ["Cómo reconstruir y ejecutar el proceso queda documentado y se entrega con él.",
                      "Cambiar el origen de datos o el modelo de datos cuenta como cambio de alcance."],
            "questions": ["¿Qué sistemas y tablas son la fuente de los datos?", "¿Con qué frecuencia debe ejecutarse el proceso?",
                          "¿Qué debe ocurrir cuando una carga falla o los datos llegan incompletos?"]},
        "design": {
            "method": ["Se muestra una primera propuesta visual antes de empezar el trabajo detallado.",
                       "Los archivos editables se entregan junto con las exportaciones finales."],
            "terms": ["Cada ronda de revisión adicional se presupuesta aparte.", "Los derechos de uso se acuerdan por escrito antes de la entrega final."],
            "questions": ["¿Qué formatos finales necesita el cliente (por ejemplo PDF, SVG, GLB, STL)?",
                          "¿Hay una guía de estilo o material de referencia que seguir?", "¿Cuántas rondas de revisión se incluyen?"]},
        "training": {
            "method": ["La sesión se adapta al nivel del equipo, que se confirma antes de empezar.",
                       "El material de apoyo se entrega al terminar la sesión."],
            "terms": ["Una sesión que se aplaza se reprograma de común acuerdo."],
            "questions": ["¿Cuántas personas asisten y con qué nivel de partida?", "¿Es presencial o a distancia, y en qué fechas?",
                          "¿Hace falta seguimiento después de la sesión?"]},
    },
}


def catalogue(lang="es"):
    """The templates with their standing sentences, for a chooser."""
    return [{"type": t, "name": NAMES[lang][t], **TEMPLATES[lang][t]} for t in TYPES]
