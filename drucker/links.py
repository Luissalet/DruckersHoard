"""Live references to the other Hoards, read through the family hub when asked and never copied.

People keeps the contacts, Ledger the money movements and Atlas the files. An engagement holds ``{app, id}`` pointers; this
module asks the owner for the current name, amount or path each time (``family.call`` through the hub with this app's own
token). Nothing it learns is stored. When the hub or the owner is not running the answer says so (``unavailable``) and the
pointer stays as it was. The same route asks Atlas for the current path and hash of a file (so a package that lists an Atlas
pointer can be verified) and Vulcan for the Khronos glTF validation of a GLB."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from . import engagements, texts
from .errors import err
from .hoard_link import _famsvc

TIMEOUT_S = 10.0
LEDGER_WINDOW_DAYS = 45


def call(owner, tool, args=None, timeout=TIMEOUT_S):
    """One tool of another Hoard through the hub, classified as in ``hoard_link._famsvc.call_tool``. Tests replace this."""
    return _famsvc.call_tool(owner, tool, args or {}, timeout_s=timeout)


def ident(value) -> str:
    """The bare id of a reference: an id, ``hoard://app/kind/id`` or ``app:id``."""
    text = str(value or "").strip()
    if text.lower().startswith("hoard://"):
        return text.rstrip("/").rsplit("/", 1)[-1]
    m = re.match(r"^(?:people|ledger|atlas):(.+)$", text, re.I)
    return m.group(1).strip() if m else text


def _state(res) -> str:
    kind = res.get("kind")
    if kind in _famsvc.UNAVAILABLE or kind == "timeout":
        return "unavailable"
    if kind == "tool_error" and res.get("status") in (404, 400):
        return "not_found"
    return "error"


def _fail(res):
    return {"state": _state(res), "detail": str(res.get("error") or "")[:300]}


def _data(res):
    data = res.get("data")
    return data if isinstance(data, dict) else {}


# ---- People
def person(ref_id, label=""):
    res = call("people", "get_person", {"person": ident(ref_id)})
    if not res.get("ok"):
        return _fail(res)
    data = _data(res)
    if data.get("candidates") or data.get("ambiguous"):
        return {"state": "not_found", "detail": texts.tr("l.ambiguous")}
    body = data.get("person") if isinstance(data.get("person"), dict) else data
    name = body.get("name") or body.get("display_name") or body.get("full_name") or ""
    if not name:
        return {"state": "not_found", "detail": texts.tr("l.no_name")}
    out = {"state": "ok", "name": name, "last_contact_at": body.get("last_contact_at"), "days_since_last_contact": data.get("days_since_last_contact")}
    if label:
        out["matches_stored"] = _same(label, name)
    return out


def _same(a, b):
    from .scope import fold
    return fold(a) == fold(b) or fold(a) in fold(b) or fold(b) in fold(a)


# ---- Ledger: no read-by-id tool, so the entry is looked up in a window of dates around the payment (or by its label)
def _entry_view(item):
    cents = item.get("amount_cents")
    amount = round(cents / 100, 2) if isinstance(cents, (int, float)) else None
    return {"state": "ok", "counterparty": item.get("counterparty") or "", "amount": amount, "date": item.get("date"),
            "account": item.get("account_name") or "", "category": item.get("category_name") or "", "note": item.get("note") or ""}


def ledger_entry(ref_id, when=None, amount=None, label=""):
    want = ident(ref_id)
    searches = []
    if when:
        try:
            d = date.fromisoformat(when)
            searches.append(("list_entries", {"from": (d - timedelta(days=LEDGER_WINDOW_DAYS)).isoformat(),
                                              "to": (d + timedelta(days=LEDGER_WINDOW_DAYS)).isoformat(), "limit": 200}))
        except ValueError:
            pass
    if label:
        searches.append(("search_entries", {"query": label[:200], "limit": 200}))
    if not searches:
        return {"state": "not_found", "detail": texts.tr("l.ledger_hint")}
    last = None
    for tool, args in searches:
        res = call("ledger", tool, args)
        if not res.get("ok"):
            last = _fail(res)
            if last["state"] == "unavailable":
                return last
            continue
        for item in _data(res).get("items") or []:
            if str(item.get("id")) == want:
                view = _entry_view(item)
                if amount is not None and view["amount"] is not None:
                    view["matches_stored"] = abs(abs(view["amount"]) - float(amount)) < 0.005
                return view
    return last or {"state": "not_found", "detail": texts.tr("l.ledger_nf", days=LEDGER_WINDOW_DAYS)}


# ---- Atlas
def atlas_id(value) -> str:
    """The Atlas file id inside a pointer: a ref ``{app, id}``, a ``{atlas: ...}`` wrapper, ``hoard://atlas/file/<id>`` or an id."""
    if isinstance(value, dict):
        inner = value.get("atlas")
        if inner not in (None, "", {}):
            return atlas_id(inner)
        return ident(value.get("id") or "")
    return ident(value)


def atlas_file(file_id):
    """Atlas's current view of one file: its live path, whether it exists and its content revision (SHA-256)."""
    res = call("atlas", "atlas_file_resolve", {"file_id": ident(file_id)})
    if not res.get("ok"):
        return _fail(res)
    data = _data(res)
    f = data.get("file") if isinstance(data.get("file"), dict) else data
    path = f.get("path") or f.get("source_path") or ""
    exists = bool(f.get("exists")) and f.get("state") != "missing"
    return {"state": "ok" if exists else "missing", "title": f.get("title") or "", "path": path, "exists": exists,
            "sha256": (f.get("revision") or "").lower() or None, "size": f.get("size"), "file_state": f.get("state"),
            "changed": data.get("changed")}


def resolve(ref, hint=None):
    """One reference, as it is now in the app that owns it."""
    app = str(ref.get("app") or "").lower()
    hint = hint or {}
    if app == "people":
        out = person(ref.get("id"), ref.get("label") or hint.get("label") or "")
    elif app == "ledger":
        out = ledger_entry(ref.get("id"), hint.get("date"), hint.get("amount"), ref.get("label") or hint.get("label") or "")
    elif app == "atlas":
        out = atlas_file(ref.get("id"))
    else:
        out = {"state": "unsupported", "detail": texts.tr("l.unsupported", app=app)}
    return {"app": app, "id": ident(ref.get("id")), **out}


def _collect(e):
    """Every pointer to another Hoard in an engagement, with where it was found and a hint for the lookup."""
    found = []
    if e.get("client_ref"):
        found.append(({"kind": "client", "id": e["id"], "title": e["client_name"]}, e["client_ref"], {"label": e["client_name"]}))
    for p in e["items"]["payment"]:
        if p.get("ledger"):
            found.append(({"kind": "payment", "id": p["id"], "title": p["title"]}, p["ledger"],
                          {"date": p.get("date"), "amount": p.get("amount"), "label": p["title"]}))
    for m in e["items"]["material"]:
        ref = m.get("atlas") or ({"app": "atlas", "id": m["ref"]} if m["kind"] == "atlas" and m.get("ref") else None)
        if ref:
            found.append(({"kind": "material", "id": m["id"], "title": m["title"]}, ref, {}))
    for d in e["deliverables"]:
        for v in d["versions"]:
            fr = v["file_ref"]
            aid = atlas_id(fr) if fr.get("atlas") else (ident(fr["ref"]) if fr.get("kind") == "atlas" and fr.get("ref") and not re.search(r"[\\/.]", fr["ref"]) else "")
            if aid:
                found.append(({"kind": "version", "id": v["id"], "title": f"{d['name']} v{v['n']}"}, {"app": "atlas", "id": aid}, {}))
    return found


@texts.localized
def engagement_refs(engagement_id):
    """The live state of every People / Ledger / Atlas pointer in the engagement. Read-only; nothing is stored."""
    e = engagements.get(engagement_id)
    found = _collect(e)
    seen = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {}
        for where, ref, hint in found:
            key = (str(ref.get("app")).lower(), ident(ref.get("id")), hint.get("date"), hint.get("amount"))
            if key not in futures:
                futures[key] = pool.submit(resolve, ref, hint)
        for key, fut in futures.items():
            try:
                seen[key] = fut.result()
            except Exception as error:  # noqa: BLE001 - a broken owner must not break the page
                seen[key] = {"app": key[0], "id": key[1], "state": "error", "detail": f"{type(error).__name__}: {error}"[:200]}
    items = []
    for where, ref, hint in found:
        key = (str(ref.get("app")).lower(), ident(ref.get("id")), hint.get("date"), hint.get("amount"))
        items.append({"where": where, "ref": {"app": ref.get("app"), "id": ref.get("id"), "label": ref.get("label", "")}, "live": seen[key]})
    counts = {}
    for it in items:
        counts[it["live"]["state"]] = counts.get(it["live"]["state"], 0) + 1
    return {"engagement_id": engagement_id, "items": items, "counts": counts, "note": texts.tr("l.note")}


# ---- Vulcan: the Khronos validator for GLB
def gltf_check(path):
    """``{state}`` ok / invalid / unavailable, with the counts Vulcan's ``gltf_validate`` reports."""
    res = call("vulcan", "gltf_validate", {"path": str(path)}, timeout=180)
    if not res.get("ok"):
        out = _fail(res)
        return {**out, "state": "unavailable" if out["state"] in ("unavailable", "not_found") else out["state"]}
    data = _data(res)
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    status = data.get("status")
    if status in ("not_installed", "timeout") or (status and status != "done"):
        return {"state": "unavailable", "detail": str(data.get("message") or status)[:200]}
    errors, warnings = int(data.get("errors") or summary.get("errors") or 0), int(data.get("warnings") or summary.get("warnings") or 0)
    return {"state": "invalid" if errors else "ok", "errors": errors, "warnings": warnings, "label": summary.get("label") or "",
            "validator_version": data.get("validator_version")}
