"""Scope comparator: initial request vs agreement vs new request. Deterministic token/sequence matching, no model.

Every request item is classified added / removed / ambiguous / already_included / unchanged. Effort is always a
range of hours with the reason; money appears only when the caller supplies an hourly-rate range."""
from __future__ import annotations

import math
import re
import unicodedata
from difflib import SequenceMatcher

from . import texts
from .errors import err

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
}  # "content" applies only to an ambiguous overlap with an agreed item; a new item with no match is never banded
INCLUDE_LIMIT_HOURS = 4
MAX_BAND_HOURS = 100000  # a saved band above this is a typo, and 1e999 (infinity) cannot be stored


def validate_bands(bands) -> dict:
    """Owner-calibrated bands: only known families/parts, each a [min, max] pair of non-negative hours with min <= max."""
    if not isinstance(bands, dict):
        raise err("e.bands")
    out: dict = {}
    for fam, parts in bands.items():
        if fam not in DEFAULT_BANDS or not isinstance(parts, dict):
            raise err("e.bands")
        for part, pair in parts.items():
            ok = (part in DEFAULT_BANDS[fam] and isinstance(pair, (list, tuple)) and len(pair) == 2
                  and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and 0 <= x <= MAX_BAND_HOURS for x in pair) and pair[0] <= pair[1])
            if not ok:
                raise err("e.bands")
            out.setdefault(fam, {})[part] = [pair[0], pair[1]]
    return out


def merge_bands(*layers) -> dict:
    """Defaults, then each layer in order (saved owner bands, then the bands of one call) overriding part by part."""
    return {fam: {**{p: list(v) for p, v in DEFAULT_BANDS[fam].items()},
                  **{p: list(v) for layer in layers for p, v in (((layer or {}).get(fam) or {}).items())}}
            for fam in DEFAULT_BANDS}


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
                item = {"id": str(entry.get("id") or f"i{n}"), "text": str(entry.get("text") or entry.get("title")).strip(),
                        "touches": entry.get("touches") or {}}
                if entry.get("hours") not in (None, ""):
                    item["hours"] = _given_hours(entry["hours"])
                out.append(item)
            else:
                raise err("e.scope_items")
        return out
    raise err("e.scope_type")


def _given_hours(value):
    """Explicit hours from the caller: a number, [min, max] or {min, max}."""
    if isinstance(value, bool):
        raise err("e.hours")
    if isinstance(value, (int, float)):
        lo = hi = value
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        lo, hi = value
    elif isinstance(value, dict):
        lo, hi = value.get("min"), value.get("max")
    else:
        raise err("e.hours")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 for v in (lo, hi)) or lo > hi:
        raise err("e.hours")
    return {"min": lo, "max": hi}


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


def _touch(dels):
    return texts.tr("s.touch", v=", ".join(dels)) if dels else ""


def estimate(item, matched, kind_hint, context, bands, rate):
    """Effort range with the reason, or ``None`` when the item is new work that cannot honestly get hours.

    Banded ranges only for a recognisable change of an agreed item (quantity, format, pipeline rework, or an ambiguous
    overlap) or when the caller gives the hours. ``kind_hint`` overrides keyword classification (e.g. quantity)."""
    dels, mils = _touched(item, context)
    text = item["text"]
    open_ms = [m for m in mils if _milestone_open(m, context)]
    if item.get("hours"):
        lo, hi = item["hours"]["min"], item["hours"]["max"]
        kind, reason = "given", texts.tr("s.eff_given", rng=f"{lo:g}-{hi:g} h" if lo != hi else f"{lo:g} h")
    elif kind_hint == "quantity":
        a, b = sorted(int(x) for x in (kind_hint_numbers(item, matched) or (1, 1)))
        delta = max(1, b - a)
        lo, hi = (v * delta for v in bands["quantity"]["per_unit"])
        kind, reason = "quantity", texts.tr("s.eff_qty", a=a, b=b, delta=delta, lo=bands["quantity"]["per_unit"][0], hi=bands["quantity"]["per_unit"][1])
    elif _has(text, PIPELINE):
        extra = max(0, len(dels) - 1) + len(open_ms)
        lo = bands["pipeline"]["base"][0] + extra * bands["pipeline"]["per_extra"][0]
        hi = bands["pipeline"]["base"][1] + extra * bands["pipeline"]["per_extra"][1]
        kind = "pipeline"
        reason = texts.tr("s.eff_pipe", dels=texts.tr("s.pipe_dels", v=", ".join(dels)) if dels else "",
                          ms=texts.tr("s.pipe_ms", v=", ".join(open_ms)) if open_ms else "")
    elif _has(text, FORMAT) and len(dels) <= 1:
        n = max(1, len(dels))
        lo, hi = (n * v for v in bands["format"]["per_deliverable"])
        kind = "format"
        reason = texts.tr("s.eff_fmt1", n=n, dels=texts.tr("s.fmt_dels", v=", ".join(dels)) if dels else "")
    elif _has(text, FORMAT):
        n = len(dels)
        lo, hi = (n * v for v in bands["format"]["per_deliverable"])
        kind = "format"
        reason = texts.tr("s.eff_fmtn", n=n, dels=", ".join(dels))
    elif matched is None:
        return {"kind": "unestimated", "hours": None, "reason": texts.tr("s.eff_unest", touch=_touch(dels)),
                "touches": {"deliverables": dels, "milestones": mils}}
    else:
        n = len(dels)
        lo = bands["content"]["base"][0] + n * bands["content"]["per_deliverable"][0]
        hi = bands["content"]["base"][1] + n * bands["content"]["per_deliverable"][1]
        kind = "content"
        reason = texts.tr("s.eff_content", touch=_touch(dels))
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
    defer = {"option": "defer", "label": texts.tr("s.o_defer"), "summary": texts.tr("s.o_defer_sum"),
             "changes_price": False, "changes_dates": False}
    if eff["kind"] == "unestimated":
        specify = {"option": "specify", "label": texts.tr("s.o_specify"), "summary": texts.tr("s.o_specify_sum"),
                   "changes_price": True, "changes_dates": True}
        return [specify, defer], "specify"
    lo, hi = eff["hours"]["min"], eff["hours"]["max"]
    rng = f"{lo:g}-{hi:g} h"
    include = {"option": "include", "label": texts.tr("s.o_include"), "summary": texts.tr("s.o_include_sum", rng=rng),
               "cost_to_us_hours": eff["hours"], "changes_price": False, "changes_dates": False}
    money = f" ({eff['money']['min']:g}-{eff['money']['max']:g} {eff['money']['currency']})" if eff.get("money") else ""
    order = {"option": "change_order", "label": texts.tr("s.o_order"), "summary": texts.tr("s.o_order_sum", rng=rng, money=money),
             "hours": eff["hours"], "money": eff.get("money"), "changes_price": True, "changes_dates": eff["kind"] == "pipeline"}
    if change_class == "ambiguous":
        rec = "clarify"
    elif eff["kind"] in ("format", "quantity", "given") and hi <= INCLUDE_LIMIT_HOURS:
        rec = "include"
    else:
        rec = "change_order"
    return [include, order, defer], rec


@texts.localized
def compare(initial=None, agreement=None, request=None, request_mode="delta", context=None, bands=None, hourly_rate=None) -> dict:
    """``request_mode``: delta (the request lists only new or changed asks) or full (it restates the whole scope, so
    agreed items it leaves out count as removed). ``context``: {deliverables:[..], milestones:[..]} used to find which
    deliverables/milestones an item touches. ``hourly_rate``: {min,max,currency} optional."""
    if request_mode not in ("delta", "full"):
        raise err("e.request_mode")
    ini, agr, req = split_items(initial), split_items(agreement), split_items(request)
    if not req:
        raise err("e.no_request")
    if not agr and not ini:
        raise err("e.no_baseline")
    context = context or {}
    merged = merge_bands(bands)
    rate = None
    if hourly_rate:
        if not all(isinstance(hourly_rate.get(k), (int, float)) and hourly_rate[k] >= 0 for k in ("min", "max")) or hourly_rate["min"] > hourly_rate["max"]:
            raise err("e.rate")
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
            cls, reason = "unchanged", texts.tr("s.same")
        elif best and score >= 0.5 and nr != nb and (nr or nb) and nr and nb:
            cls, hint = "ambiguous", "quantity"
            reason = texts.tr("s.qty", old=", ".join(sorted(nb)), new=", ".join(sorted(nr)))
        elif best and score >= 0.5 and neg:
            cls, reason = "ambiguous", texts.tr("s.negation")
        elif best and contain >= 0.8 and len(set(tokens(r["text"]))) >= 2 and score >= 0.4:
            cls, reason = "already_included", texts.tr("s.included")
        elif best and (score >= 0.4 or contain >= 0.5):
            cls, reason = "ambiguous", texts.tr("s.overlap")
        else:
            cls, reason = "added", texts.tr("s.added")
            best = None if score < 0.2 else best
        entry = {"id": r["id"], "text": r["text"], "class": cls, "reason": reason, "estimated": True,
                 "match": {"id": best["id"], "text": best["text"], "score": score, "containment": contain} if best else None}
        if cls == "added" and ini and agr:
            dropped = max(((*similarity(r["text"], i["text"]), i) for i in ini), key=lambda s: s[0])
            if dropped[0] >= 0.5:
                entry["note"] = texts.tr("s.dropped", text=dropped[2]["text"])
        if cls in ("added", "ambiguous"):
            eff = estimate(r, best if cls == "ambiguous" else None, hint, context, merged, rate)
            if eff["kind"] == "unestimated":
                entry["estimated"] = False
            elif cls == "ambiguous" and eff["kind"] != "given":
                eff["hours"]["min"] = 0.0
                eff["reason"] += texts.tr("s.min_zero")
                if eff.get("money"):
                    eff["money"]["min"] = 0.0
            entry["effort"] = eff
            entry["alternatives"], entry["recommended"] = alternatives(cls, eff)
        elif cls == "already_included":
            entry["effort"] = {"kind": "none", "hours": _range(0, 0), "reason": texts.tr("s.already")}
        else:
            entry["effort"] = {"kind": "none", "hours": _range(0, 0), "reason": texts.tr("s.nochange")}
        items.append(entry)
    removed = []
    if request_mode == "full":
        matched = {i["match"]["id"] for i in items if i["match"] and i["class"] != "added"}
        for b in baseline:
            if b["id"] in matched:
                continue
            removed.append({"id": b["id"], "text": b["text"], "class": "removed",
                            "reason": texts.tr("s.removed"),
                            "effort": {"kind": "removal", "hours": _range(0, 0), "reason": texts.tr("s.removal"), "direction": "save"}})
    counts = {c: 0 for c in CLASSES}
    for e in items + removed:
        counts[e["class"]] += 1
    est = [i for i in items if i["effort"]["hours"] is not None]
    firm = sum(i["effort"]["hours"]["max"] for i in est if i["class"] == "added")
    firm_lo = sum(i["effort"]["hours"]["min"] for i in est if i["class"] == "added")
    amb_hi = sum(i["effort"]["hours"]["max"] for i in est if i["class"] == "ambiguous")
    return {"counts": counts, "items": items, "removed": removed,
            "totals": {"hours": _range(firm_lo, firm + amb_hi), "certain_hours": _range(firm_lo, firm), "uncertain_hours_max": round(amb_hi, 1),
                       "unestimated_items": sum(1 for i in items if i["estimated"] is False)},
            "baseline": "agreement" if agr else "initial request", "request_mode": request_mode, "lang": texts.cur(), "bands": merged,
            "method": texts.tr("s.method")}
