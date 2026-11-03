"""Proposal preparer: a draft from the stored engagement where every sentence is tagged verified, assumption or question."""
from __future__ import annotations

import html
import re

from . import engagements
from .errors import DruckerError
from .scope import fold

TAGS = ("verified", "assumption", "question")

T = {
    "en": {
        "title": "Proposal", "legend": "Draft for review. Each line is tagged: verified (backed by a stored fact), assumption, or question.",
        "sections": {"problem": "Problem", "scope": "Scope", "milestones": "Milestones", "deliverables": "Deliverables", "decisions": "Agreed decisions",
                     "budget": "Budget", "assumptions": "Assumptions", "questions": "Open questions"},
        "client": "Client: {v}.", "no_client": "Who is the client contact for this proposal?", "no_problem": "What problem should the client's work solve?",
        "scope_agreed": "{t}.", "scope_prop": "Proposed, not yet agreed: {t}.", "no_scope": "Which items are in the scope?",
        "ms_dated": "{t}: {d}.", "ms_undated": "The date for milestone \"{t}\" is not set.", "no_ms": "What milestones and dates apply?",
        "dl": "{n}: {c} version(s) on file.", "dec": "{w}{y}{d}.", "because": ", because {v}", "on": " ({d})",
        "budget": "Budget range: {a} to {b} {c}.", "budget_max": "Budget up to {b} {c}.", "budget_min": "Budget from {a} {c}.",
        "budget_assume": "The amount is an estimate inside this range and holds only while the scope stays as listed; changes are priced separately as ranges.",
        "no_budget": "What budget range does the client have in mind?"},
    "es": {
        "title": "Propuesta", "legend": "Borrador para revisar. Cada línea lleva una etiqueta: verificado (respaldado por un dato guardado), supuesto o pregunta.",
        "sections": {"problem": "Problema", "scope": "Alcance", "milestones": "Hitos", "deliverables": "Entregables", "decisions": "Decisiones acordadas",
                     "budget": "Presupuesto", "assumptions": "Supuestos", "questions": "Preguntas abiertas"},
        "client": "Cliente: {v}.", "no_client": "¿Quién es el contacto del cliente para esta propuesta?", "no_problem": "¿Qué problema debe resolver el trabajo del cliente?",
        "scope_agreed": "{t}.", "scope_prop": "Propuesto, aún no acordado: {t}.", "no_scope": "¿Qué elementos entran en el alcance?",
        "ms_dated": "{t}: {d}.", "ms_undated": "La fecha del hito «{t}» no está fijada.", "no_ms": "¿Qué hitos y fechas se aplican?",
        "dl": "{n}: {c} versión(es) registradas.", "dec": "{w}{y}{d}.", "because": ", porque {v}", "on": " ({d})",
        "budget": "Rango de presupuesto: de {a} a {b} {c}.", "budget_max": "Presupuesto hasta {b} {c}.", "budget_min": "Presupuesto desde {a} {c}.",
        "budget_assume": "El importe es una estimación dentro de este rango y se mantiene solo mientras el alcance siga como se lista; los cambios se presupuestan aparte como rangos.",
        "no_budget": "¿Qué rango de presupuesto tiene en mente el cliente?"},
}
TAG_LABEL = {"en": {"verified": "verified", "assumption": "assumption", "question": "question"},
             "es": {"verified": "verificado", "assumption": "supuesto", "question": "pregunta"}}


def _num(v):
    return f"{v:,.0f}".replace(",", " ") if float(v).is_integer() else f"{v:,.2f}".replace(",", " ")


def build(engagement_id, lang="es", denylist=None):
    if lang not in T:
        raise DruckerError("lang must be es or en")
    t = T[lang]
    e = engagements.get(engagement_id)
    sentences = []

    def add(section, tag, text, kind=None, ref=None, field=None):
        if tag == "verified" and not kind:
            raise AssertionError("verified sentence without a source")
        sentences.append({"id": f"s{len(sentences) + 1}", "section": section, "tag": tag, "text": text,
                          "source": {"kind": kind, "id": ref, "field": field} if kind else None})

    if e["client_name"]:
        add("problem", "verified", t["client"].format(v=e["client_name"]), "engagement", e["id"], "client_name")
    else:
        add("problem", "question", t["no_client"])
    if e["origin"].strip():
        add("problem", "verified", e["origin"].strip().rstrip(".") + ".", "engagement", e["id"], "origin")
    else:
        add("problem", "question", t["no_problem"])
    scope = [i for i in e["items"]["scope"] if i["status"] != "dropped"]
    for i in scope:
        text = i["title"] + (f": {i['detail']}" if i["detail"] else "")
        if i["status"] in ("agreed", "done"):
            add("scope", "verified", t["scope_agreed"].format(t=text.rstrip(".")), "scope", i["id"], "title")
        else:
            add("scope", "assumption", t["scope_prop"].format(t=text.rstrip(".")), "scope", i["id"], "title")
    if not scope:
        add("scope", "question", t["no_scope"])
    for m in e["items"]["milestone"]:
        if m["due"]:
            add("milestones", "verified", t["ms_dated"].format(t=m["title"].rstrip("."), d=m["due"]), "milestone", m["id"], "due")
        else:
            add("milestones", "question", t["ms_undated"].format(t=m["title"]), "milestone", m["id"], "due")
    if not e["items"]["milestone"]:
        add("milestones", "question", t["no_ms"])
    for d in e["deliverables"]:
        add("deliverables", "verified", t["dl"].format(n=d["name"], c=len(d["versions"])), "deliverable", d["id"], "name")
    for d in e["items"]["decision"]:
        why = t["because"].format(v=d["why"].rstrip(".")) if d["why"] else ""
        on = t["on"].format(d=d["date"]) if d["date"] else ""
        add("decisions", "verified", t["dec"].format(w=d["what"].rstrip("."), y=why, d=on), "decision", d["id"], "what")
    lo, hi, cur = e["budget_min"], e["budget_max"], e["currency"]
    if lo is not None and hi is not None:
        add("budget", "verified", t["budget"].format(a=_num(lo), b=_num(hi), c=cur), "engagement", e["id"], "budget")
    elif hi is not None:
        add("budget", "verified", t["budget_max"].format(b=_num(hi), c=cur), "engagement", e["id"], "budget_max")
    elif lo is not None:
        add("budget", "verified", t["budget_min"].format(a=_num(lo), c=cur), "engagement", e["id"], "budget_min")
    else:
        add("budget", "question", t["no_budget"])
    if lo is not None or hi is not None:
        add("budget", "assumption", t["budget_assume"])
    for a in e["items"]["assumption"]:
        add("assumptions", "assumption", a["text"].rstrip(".") + ".", "assumption", a["id"], "text")
    for q in e["items"]["question"]:
        if q["status"] == "open":
            add("questions", "question", q["text"].rstrip("?").strip() + "?" if not q["text"].rstrip().endswith("?") else q["text"].strip(), "question", q["id"], "text")
    words = denylist if denylist is not None else (e["denylist"] if e["denylist"] is not None else engagements.get_settings()["denylist"])
    title = f"{t['title']}: {e['name']}"
    violations = check_denylist(sentences, title, words)
    counts = {tag: sum(1 for s in sentences if s["tag"] == tag) for tag in TAGS}
    return {"engagement_id": e["id"], "lang": lang, "title": title, "legend": t["legend"], "sections": t["sections"],
            "sentences": sentences, "counts": counts, "denylist": words, "violations": violations,
            "client_ready": not violations}


def check_denylist(sentences, title, words):
    """Internal names must not reach client-facing material. Case/accent-insensitive whole-word match (plural s allowed).
    The client's own name field is not scanned: it is the client's name, not ours."""
    out = []
    rules = [(w, re.compile(r"(?<![a-z0-9])" + re.escape(fold(w)) + r"s?(?![a-z0-9])")) for w in words if fold(w)]
    scan = [("title", title)] + [(s["id"], s["text"]) for s in sentences if not (s["source"] and s["source"]["field"] == "client_name")]
    for ident, text in scan:
        folded = fold(text)
        for word, rx in rules:
            if rx.search(folded):
                out.append({"term": word, "sentence_id": ident, "text": text})
    return out


def render(draft, fmt):
    if fmt not in ("md", "html"):
        raise DruckerError("format must be md or html")
    if draft["violations"]:
        terms = sorted({v["term"] for v in draft["violations"]})
        raise DruckerError("Refused: client-facing material would contain internal names: " + ", ".join(terms),
                           violations=draft["violations"])
    labels = TAG_LABEL[draft["lang"]]
    by = {}
    for s in draft["sentences"]:
        by.setdefault(s["section"], []).append(s)
    order = [k for k in draft["sections"] if k in by]
    if fmt == "md":
        lines = [f"# {draft['title']}", "", f"_{draft['legend']}_", ""]
        for key in order:
            lines += [f"## {draft['sections'][key]}", ""] + [f"- {s['text']} `[{labels[s['tag']]}]`" for s in by[key]] + [""]
        return "\n".join(lines).rstrip() + "\n"
    e = html.escape
    parts = [f"<!doctype html><html lang=\"{draft['lang']}\"><head><meta charset=\"utf-8\"><title>{e(draft['title'])}</title>",
             "<style>body{font:16px/1.5 Georgia,serif;max-width:46rem;margin:2rem auto;padding:0 1rem;color:#222}"
             ".t{font:12px sans-serif;padding:1px 6px;border-radius:8px;margin-left:.4rem;white-space:nowrap}"
             ".verified{background:#dff3e4}.assumption{background:#fff1c9}.question{background:#dfe9fb}</style></head><body>",
             f"<h1>{e(draft['title'])}</h1><p><em>{e(draft['legend'])}</em></p>"]
    for key in order:
        parts.append(f"<h2>{e(draft['sections'][key])}</h2><ul>")
        parts += [f"<li>{e(s['text'])}<span class=\"t {s['tag']}\">{e(labels[s['tag']])}</span></li>" for s in by[key]]
        parts.append("</ul>")
    return "".join(parts) + "</body></html>\n"


def proposal(engagement_id, fmt="json", lang="es", denylist=None):
    draft = build(engagement_id, lang, denylist)
    if fmt == "json":
        return draft
    return {"format": fmt, "title": draft["title"], "content": render(draft, fmt), "counts": draft["counts"]}
