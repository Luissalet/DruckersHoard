"""The commercial answer to a scope request, written into the decision log, and the report of accepted change orders.

When a comparison shows a request outside the agreement the owner picks one of the options (include it, change order with its
range, defer it, specify it first). ``decide`` turns that pick into a decision of the engagement (what, why, who, date, the hours
and money range that were on the table) and, for include and change order, into an agreed scope item marked as a change. The
report lists the change orders in force: when a request was decided more than once, only the latest decision counts."""
from __future__ import annotations

from datetime import date as _date

from . import engagements, scope, texts
from .errors import err
from .models import OPTIONS


def _range(h):
    return f"{h['min']:g}-{h['max']:g} h" if h["min"] != h["max"] else f"{h['min']:g} h"


def _hours(value):
    if value in (None, ""):
        return None
    return scope._given_hours(value)


def _money(value):
    if value in (None, "", {}):
        return None
    if isinstance(value, dict) and all(isinstance(value.get(k), (int, float)) and not isinstance(value.get(k), bool) for k in ("min", "max")) \
            and 0 <= value["min"] <= value["max"]:
        return {"min": value["min"], "max": value["max"], "currency": str(value.get("currency") or "EUR").upper()}
    raise err("e.money")


@texts.localized
def decide(engagement_id, request, option, hours=None, money=None, why="", who="", date=None, add_to_scope=True):
    """Record the option chosen for ``request``. Returns the decision, the scope item it created (if any) and a summary line."""
    request = (request or "").strip()
    if not request:
        raise err("e.request_text")
    if option not in OPTIONS:
        raise err("e.option", options=", ".join(OPTIONS))
    hours, money = _hours(hours), _money(money)
    if option == "change_order" and hours is None:
        raise err("e.co_hours")
    rng = f" ({_range(hours)})" if hours else ""
    body = {"what": texts.tr("d.what." + option, request=request.rstrip(".;"), rng=rng), "why": (why or "").strip(), "who": (who or "").strip(),
            "date": date or _date.today().isoformat(), "option": option, "request": request}
    if hours:
        body["hours"] = hours
    if money:
        body["money"] = money
    engagements.get(engagement_id)  # a missing engagement is refused before anything is written
    decision = engagements.save_item(engagement_id, "decision", body)
    item = None
    if add_to_scope and option in ("include", "change_order"):
        have = {scope.fold(i["title"]) for i in engagements.get(engagement_id)["items"]["scope"]}
        if scope.fold(request) not in have:
            item = engagements.save_item(engagement_id, "scope", {"title": request, "status": "agreed", "origin": "change",
                                                                 "detail": texts.tr("d.scope_detail." + option, rng=_range(hours) if hours else "")})
    return {"decision": decision, "scope_item": item, "summary": texts.tr("d.done." + option, request=request, rng=rng)}


def _sum_hours(rows):
    return {"min": round(sum(r["hours"]["min"] for r in rows if r.get("hours")), 1), "max": round(sum(r["hours"]["max"] for r in rows if r.get("hours")), 1)}


def _row(d):
    return {"decision_id": d["id"], "request": d.get("request") or d["what"], "option": d["option"], "hours": d.get("hours"), "money": d.get("money"),
            "date": d.get("date"), "who": d.get("who", ""), "why": d.get("why", ""), "what": d["what"]}


@texts.localized
def change_orders(engagement_id, fmt="json"):
    """Change orders accepted for the engagement, with the range and the decision taken, plus what was included, deferred or
    sent to be specified. ``fmt`` md adds the same report as Markdown in ``content``."""
    if fmt not in ("json", "md"):
        raise err("e.format_json_md")
    e = engagements.get(engagement_id)
    latest, older = {}, []
    for d in e["items"]["decision"]:
        if not d.get("option"):
            continue
        key = scope.fold(d.get("request") or d["what"])
        if key in latest:
            older.append({**_row(latest[key]), "superseded_by": d["id"]})
        latest[key] = d
    rows = [_row(d) for d in latest.values()]
    accepted = [r for r in rows if r["option"] == "change_order"]
    other = {o: [r for r in rows if r["option"] == o] for o in ("include", "defer", "specify")}
    money = {}
    for r in accepted:
        if r["money"]:
            m = money.setdefault(r["money"]["currency"], {"min": 0.0, "max": 0.0})
            m["min"] += r["money"]["min"]
            m["max"] += r["money"]["max"]
    out = {"engagement_id": e["id"], "engagement": e["name"], "currency": e["currency"], "change_orders": accepted,
           "totals": {"count": len(accepted), "hours": _sum_hours(accepted),
                      "money": {c: {"min": round(v["min"], 2), "max": round(v["max"], 2)} for c, v in money.items()},
                      "money_complete": all(r["money"] for r in accepted)},
           "included": other["include"], "deferred": other["defer"], "to_specify": other["specify"], "superseded": older,
           "budget": {"min": e["budget_min"], "max": e["budget_max"], "currency": e["currency"]}}
    if fmt == "md":
        out["content"] = _markdown(out)
    return out


def _line(r):
    bits = [f"**{r['request'].rstrip('.;')}**"]
    if r["hours"]:
        bits.append(_range(r["hours"]))
    if r["money"]:
        bits.append(f"{r['money']['min']:g}-{r['money']['max']:g} {r['money']['currency']}")
    meta = [x for x in (r["date"], r["who"]) if x]
    line = "- " + " · ".join(bits) + (f" ({', '.join(meta)})" if meta else "")
    return line + (f" — {r['why']}" if r["why"] else "")


def _markdown(o):
    lines = [f"# {texts.tr('d.rep.title', name=o['engagement'])}", "", f"_{texts.tr('d.rep.note')}_", "", f"## {texts.tr('d.rep.accepted')}", ""]
    lines += [_line(r) for r in o["change_orders"]] or [texts.tr("d.rep.none")]
    t = o["totals"]
    if o["change_orders"]:
        total = f"{texts.tr('d.rep.total')}: {t['count']} · {_range(t['hours'])}"
        for cur, m in t["money"].items():
            total += f" · {m['min']:g}-{m['max']:g} {cur}"
        if t["money"] and not t["money_complete"]:
            total += f" ({texts.tr('d.rep.partial')})"
        lines += ["", f"**{total}**"]
    for key, title in (("included", "d.rep.included"), ("deferred", "d.rep.deferred"), ("to_specify", "d.rep.specify")):
        if o[key]:
            lines += ["", f"## {texts.tr(title)}", ""] + [_line(r) for r in o[key]]
    if o["superseded"]:
        lines += ["", f"## {texts.tr('d.rep.superseded')}", ""] + [_line(r) + f" [{texts.tr('d.opt.' + r['option'])}]" for r in o["superseded"]]
    return "\n".join(lines) + "\n"
