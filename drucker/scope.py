"""Scope comparator: initial request vs agreement vs new request. Deterministic token/sequence matching, no model.

Every request item is classified added / removed / ambiguous / already_included / unchanged. Effort is always a
range of hours with the reason; money appears only when the caller supplies an hourly-rate range."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from .errors import DruckerError

CLASSES = ("added", "removed", "ambiguous", "already_included", "unchanged")
STOP = set("a al algo and as at con de del el ella en es esta este for from i in is la las lo los me mi of on or para por que se si "
           "su sus the to un una uno unos unas y o the we our us it its be by also tambien ademas queremos quiero need want please "
           "por favor like would should debe deben has have".split())
NEGATIONS = {"sin", "no", "not", "without", "nunca", "never", "excluye", "excluding", "except", "excepto"}
PIPELINE = ("pipeline", "flujo", "proceso", "integr", "automat", "rehac", "rework", "arquitect", "base datos", "database", "migr",
            "api", "backend", "modelo dato", "datos entrada", "import", "sincroniz", "conect", "origen dato", "etl", "calcul")
FORMAT = ("format", "pdf", "png", "svg", "jpg", "jpeg", "docx", "xlsx", "csv", "html", "epub", "mp4", "glb", "stl", "export",
          "exportar", "color", "tamano", "size", "resolu", "tipograf", "font", "idioma", "language", "traduc", "translat", "logo")
DEFAULT_BANDS = {  # hours; a starting point to calibrate, never a quote
    "format": {"per_deliverable": [1, 4]},
    "content": {"base": [4, 12], "per_deliverable": [2, 4]},
    "pipeline": {"base": [16, 40], "per_extra": [4, 10]},
    "quantity": {"per_unit": [1, 3]},
    "clarify": {"base": [0, 0]},
}
INCLUDE_LIMIT_HOURS = 4


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text.lower())).strip()


def stem(word: str) -> str:
    if word.isdigit():
        return word
    for suffix in ("aciones", "ciones", "cion", "ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[:-len(suffix)]
    return word


def tokens(text: str) -> list[str]:
    return [stem(w) for w in fold(text).split() if w not in STOP or w in NEGATIONS]


def numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+", fold(text)))


def similarity(a: str, b: str) -> tuple[float, float]:
    """(score, containment of a in b). score blends token overlap with ordered sequence similarity."""
    ta, tb = tokens(a), tokens(b)
    sa, sb = set(ta), set(tb)
    if not sa or not sb:
        return 0.0, 0.0
    jaccard = len(sa & sb) / len(sa | sb)
    ratio = SequenceMatcher(None, ta, tb).ratio()
    return round(0.5 * jaccard + 0.5 * ratio, 3), round(len(sa & sb) / len(sa), 3)


def split_items(source) -> list[dict]:
    """Text (bullets/lines/sentences) or a list of strings / {id,text,touches}."""
    if source in (None, "", []):
        return []
    if isinstance(source, str):
        parts = []
        for line in source.splitlines():
            line = re.sub(r"^\s*(?:[-*•–]|\d+[.)])\s*", "", line).strip()
            parts += [p.strip() for p in re.split(r"(?<=[.;!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡0-9])", line) if p.strip()]
        return [{"id": f"i{n}", "text": p.rstrip(".;")} for n, p in enumerate(parts, 1)]
    if isinstance(source, list):
        out = []
        for n, entry in enumerate(source, 1):
            if isinstance(entry, str) and entry.strip():
                out.append({"id": f"i{n}", "text": entry.strip()})
            elif isinstance(entry, dict) and str(entry.get("text") or entry.get("title") or "").strip():
                out.append({"id": str(entry.get("id") or f"i{n}"), "text": str(entry.get("text") or entry.get("title")).strip(),
                            "touches": entry.get("touches") or {}})
            else:
                raise DruckerError("Scope items must be text or objects with a text field")
        return out
    raise DruckerError("Scope must be text or a list of items")


def _has(text, words):
    f = " " + fold(text)
    return any((" " + w) in f for w in words)


def _touched(item, context):
    touches = item.get("touches") or {}
    dels, mils = list(touches.get("deliverables") or []), list(touches.get("milestones") or [])
    t = set(tokens(item["text"]))
    for key, names, out in (("deliverables", context.get("deliverables") or [], dels), ("milestones", context.get("milestones") or [], mils)):
        for entry in names:
            name = entry if isinstance(entry, str) else entry.get("name") or entry.get("title") or ""
            nt = set(tokens(name))
            shared = nt & t
            if nt and name not in out and (len(shared) / len(nt) >= 0.6 or (len(shared) / len(nt) >= 0.33 and any(len(w) >= 5 for w in shared))):
                out.append(name)
    return dels, mils


def _milestone_open(name, context):
    for entry in context.get("milestones") or []:
        if isinstance(entry, dict) and (entry.get("title") or entry.get("name")) == name:
            return entry.get("status", "planned") != "done"
    return True


def _range(lo, hi):
    return {"min": round(lo, 1), "max": round(hi, 1)}


def estimate(item, matched, kind_hint, context, bands, rate):
    """Effort range with the reason. ``kind_hint`` overrides keyword classification (e.g. quantity)."""
    dels, mils = _touched(item, context)
    text = item["text"]
    open_ms = [m for m in mils if _milestone_open(m, context)]
    if kind_hint == "quantity":
        a, b = sorted(int(x) for x in (kind_hint_numbers(item, matched) or (1, 1)))
        delta = max(1, b - a)
        lo, hi = (v * delta for v in bands["quantity"]["per_unit"])
        kind, reason = "quantity", (f"Quantity changes from {a} to {b}: about {delta} more unit(s) at {bands['quantity']['per_unit'][0]}-"
                                    f"{bands['quantity']['per_unit'][1]} h each; the process itself does not change.")
    elif _has(text, PIPELINE):
        extra = max(0, len(dels) - 1) + len(open_ms)
        lo = bands["pipeline"]["base"][0] + extra * bands["pipeline"]["per_extra"][0]
        hi = bands["pipeline"]["base"][1] + extra * bands["pipeline"]["per_extra"][1]
        kind = "pipeline"
        reason = ("Changes how the work is produced, not just how it looks: it touches an earlier stage, so everything after it is redone "
                  "and revalidated" + (f" (deliverables: {', '.join(dels)})" if dels else "") +
                  (f" (open milestones: {', '.join(open_ms)})" if open_ms else "") + ".")
    elif _has(text, FORMAT) and len(dels) <= 1:
        n = max(1, len(dels))
        lo, hi = (n * v for v in bands["format"]["per_deliverable"])
        kind = "format"
        reason = (f"Output format change on {n} deliverable(s)" + (f" ({', '.join(dels)})" if dels else "") +
                  "; it touches only the last stage, no earlier milestone is reopened.")
    elif _has(text, FORMAT):
        n = len(dels)
        lo, hi = (n * v for v in bands["format"]["per_deliverable"])
        kind = "format"
        reason = f"Output format change repeated across {n} deliverables ({', '.join(dels)}); still last-stage work only."
    else:
        n = len(dels)
        lo = bands["content"]["base"][0] + n * bands["content"]["per_deliverable"][0]
        hi = bands["content"]["base"][1] + n * bands["content"]["per_deliverable"][1]
        kind = "content"
        reason = ("New work item with no close match in the agreement" + (f"; it touches {', '.join(dels)}" if dels else "") +
                  ". Range from the default band; refine once the item is specified.")
    out = {"kind": kind, "hours": _range(lo, hi), "reason": reason, "touches": {"deliverables": dels, "milestones": mils}}
    if rate:
        out["money"] = {"min": round(lo * rate["min"], 2), "max": round(hi * rate["max"], 2), "currency": rate.get("currency", "")}
    return out


def kind_hint_numbers(item, matched):
    new, old = sorted(numbers(item["text"]), key=int), sorted(numbers(matched["text"]), key=int) if matched else []
    if not new or not old:
        return None
    return int(old[-1]), int(new[-1])


def alternatives(change_class, eff, rate_currency=""):
    lo, hi = eff["hours"]["min"], eff["hours"]["max"]
    rng = f"{lo:g}-{hi:g} h"
    include = {"option": "include", "label": "Include in the current scope",
               "summary": f"Absorb {rng} inside the agreed price and dates.",
               "cost_to_us_hours": eff["hours"], "changes_price": False, "changes_dates": False}
    order = {"option": "change_order", "label": "Change order with a range",
             "summary": f"Agree in writing an extra {rng}" + (f" ({eff['money']['min']:g}-{eff['money']['max']:g} {eff['money']['currency']})" if eff.get("money") else "") +
                        "; confirm whether milestones move.",
             "hours": eff["hours"], "money": eff.get("money"), "changes_price": True, "changes_dates": eff["kind"] == "pipeline"}
    defer = {"option": "defer", "label": "Defer to a later phase",
             "summary": "Keep the current scope and dates; schedule this separately after delivery.",
             "changes_price": False, "changes_dates": False}
    if change_class == "ambiguous":
        rec = "clarify"
    elif eff["kind"] in ("format", "quantity") and hi <= INCLUDE_LIMIT_HOURS:
        rec = "include"
    elif eff["kind"] == "pipeline" or hi > 16:
        rec = "change_order"
    else:
        rec = "change_order"
    return [include, order, defer], rec


def compare(initial=None, agreement=None, request=None, request_mode="delta", context=None, bands=None, hourly_rate=None) -> dict:
    """``request_mode``: delta (the request lists only new or changed asks) or full (it restates the whole scope, so
    agreed items it leaves out count as removed). ``context``: {deliverables:[..], milestones:[..]} used to find which
    deliverables/milestones an item touches. ``hourly_rate``: {min,max,currency} optional."""
    if request_mode not in ("delta", "full"):
        raise DruckerError("request_mode must be delta or full")
    ini, agr, req = split_items(initial), split_items(agreement), split_items(request)
    if not req:
        raise DruckerError("The new request has no items")
    if not agr and not ini:
        raise DruckerError("Give the agreement or the initial request to compare against")
    context = context or {}
    merged = {k: {**DEFAULT_BANDS[k], **((bands or {}).get(k) or {})} for k in DEFAULT_BANDS}
    rate = None
    if hourly_rate:
        if not all(isinstance(hourly_rate.get(k), (int, float)) and hourly_rate[k] >= 0 for k in ("min", "max")) or hourly_rate["min"] > hourly_rate["max"]:
            raise DruckerError("hourly_rate needs numeric min <= max")
        rate = hourly_rate
    baseline = agr or ini
    items = []
    for r in req:
        scored = sorted(((*similarity(r["text"], b["text"]), b) for b in baseline), key=lambda s: (-s[0], -s[1]))
        score, contain, best = scored[0] if scored else (0.0, 0.0, None)
        cls, reason, hint = None, "", None
        nr, nb = (numbers(r["text"]), numbers(best["text"])) if best else (set(), set())
        neg = best and (bool(NEGATIONS & set(fold(r["text"]).split())) != bool(NEGATIONS & set(fold(best["text"]).split())))
        if best and score >= 0.85 and nr == nb and not neg:
            cls, reason = "unchanged", "Same as an agreed item."
        elif best and score >= 0.5 and nr != nb and (nr or nb) and nr and nb:
            cls, hint = "ambiguous", "quantity"
            reason = f"Looks like the agreed item but the number changes ({', '.join(sorted(nb))} -> {', '.join(sorted(nr))})."
        elif best and score >= 0.5 and neg:
            cls, reason = "ambiguous", "Similar to an agreed item but it flips an exclusion or negation."
        elif best and contain >= 0.8 and len(set(tokens(r["text"]))) >= 2 and score >= 0.4:
            cls, reason = "already_included", "Wording differs but everything it asks is in an agreed item."
        elif best and (score >= 0.4 or contain >= 0.5):
            cls, reason = "ambiguous", "Overlaps an agreed item but asks for more or something different; not certain."
        else:
            cls, reason = "added", "No agreed item covers it."
            best = None if score < 0.2 else best
        entry = {"id": r["id"], "text": r["text"], "class": cls, "reason": reason,
                 "match": {"id": best["id"], "text": best["text"], "score": score, "containment": contain} if best else None}
        if cls == "added" and ini and agr:
            dropped = max(((*similarity(r["text"], i["text"]), i) for i in ini), key=lambda s: s[0])
            if dropped[0] >= 0.5:
                entry["note"] = f"It was in the initial request ({dropped[2]['text']!r}) and is not in the agreement."
        if cls in ("added", "ambiguous"):
            eff = estimate(r, best if cls == "ambiguous" else None, hint, context, merged, rate)
            if cls == "ambiguous":
                eff["hours"]["min"] = 0.0
                eff["reason"] += " Minimum is zero because it may already be covered once clarified."
                if eff.get("money"):
                    eff["money"]["min"] = 0.0
            entry["effort"] = eff
            entry["alternatives"], entry["recommended"] = alternatives(cls, eff)
        elif cls == "already_included":
            entry["effort"] = {"kind": "none", "hours": _range(0, 0), "reason": "Already part of the agreement; no extra work to price."}
        else:
            entry["effort"] = {"kind": "none", "hours": _range(0, 0), "reason": "No change."}
        items.append(entry)
    removed = []
    if request_mode == "full":
        matched = {i["match"]["id"] for i in items if i["match"] and i["class"] != "added"}
        for b in baseline:
            if b["id"] in matched:
                continue
            removed.append({"id": b["id"], "text": b["text"], "class": "removed",
                            "reason": "Agreed, but the new request does not mention it.",
                            "effort": {"kind": "removal", "hours": _range(0, 0), "reason": "Work already done on it is not recoverable; "
                                       "any saving applies only to work not yet started. Confirm status before crediting.", "direction": "save"}})
    counts = {c: 0 for c in CLASSES}
    for e in items + removed:
        counts[e["class"]] += 1
    firm = sum(i["effort"]["hours"]["max"] for i in items if i["class"] == "added")
    firm_lo = sum(i["effort"]["hours"]["min"] for i in items if i["class"] == "added")
    amb_hi = sum(i["effort"]["hours"]["max"] for i in items if i["class"] == "ambiguous")
    return {"counts": counts, "items": items, "removed": removed,
            "totals": {"hours": _range(firm_lo, firm + amb_hi), "certain_hours": _range(firm_lo, firm), "uncertain_hours_max": round(amb_hi, 1)},
            "baseline": "agreement" if agr else "initial request", "request_mode": request_mode,
            "method": "Deterministic token and sequence similarity. Effort ranges follow editable rule bands and the deliverables each item touches; "
                      "they are not prices and not a quote. Uncertain matches are marked ambiguous, never forced."}
