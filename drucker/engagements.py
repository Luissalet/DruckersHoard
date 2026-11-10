"""Engagement file: client, scope, milestones, materials, decisions, payments and the history of every change."""
from __future__ import annotations

from pydantic import ValidationError

from . import db, scope, texts
from .errors import DruckerError, err, not_found
from .models import ITEM_KINDS, ITEM_MODELS, EngagementIn

DEFAULT_DENYLIST = ["Faustus", "Hoard", "Drucker", "Atlas", "Ledger", "MCP", "Copilot", "Claude", "Codex"]
ENG_FIELDS = list(EngagementIn.model_fields)
JSON_FIELDS = ("client_ref", "denylist")


def _validate(model, data):
    try:
        return model.model_validate(data)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        msg = texts.tr("e.budget") if first["type"] == "value_error" and "budget_min" in first["msg"] else texts.pyd(first["type"]) if texts.cur() == "es" else first["msg"]
        raise DruckerError(f"{where}: {msg}" if where else msg) from None


def _row_eng(row):
    out = {k: row[k] for k in ("id", "created", "updated", "name", "client_name", "origin", "status", "currency",
                              "budget_min", "budget_max", "notes")}
    out["kind"] = row["kind"] or "general"
    out["client_ref"] = db.loads(row["client_ref"])
    out["denylist"] = db.loads(row["denylist"])
    return out


def _require(conn, engagement_id):
    row = conn.execute("SELECT * FROM engagements WHERE id=?", (engagement_id,)).fetchone()
    if not row:
        raise not_found("e.not_found_eng", id=engagement_id)
    return row


def list_engagements(status=None, query=None):
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM engagements ORDER BY updated DESC, rowid DESC").fetchall()
        counts = {r[0]: r[1] for r in conn.execute(
            "SELECT engagement_id, COUNT(*) FROM items WHERE kind='milestone' GROUP BY engagement_id")}
    out = []
    for row in rows:
        e = _row_eng(row)
        if status and e["status"] != status:
            continue
        if query and query.lower() not in (e["name"] + " " + e["client_name"]).lower():
            continue
        e["milestones"] = counts.get(e["id"], 0)
        out.append(e)
    return out


def _items(conn, engagement_id, kind=None):
    sql, args = "SELECT * FROM items WHERE engagement_id=?", [engagement_id]
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    # "_k" is the kind of the row; payments and materials carry their own "kind" field, which must not decide where they are listed
    return [{"id": r["id"], "kind": r["kind"], **db.loads(r["body"]), "created": r["created"], "updated": r["updated"], "_k": r["kind"]}
            for r in conn.execute(sql + " ORDER BY seq, rowid", args)]


def get(engagement_id):
    from . import review
    with db.connect() as conn:
        e = _row_eng(_require(conn, engagement_id))
        items = _items(conn, engagement_id)
        e["items"] = {k: [{n: v for n, v in i.items() if n != "_k"} for i in items if i["_k"] == k] for k in ITEM_KINDS}
        e["deliverables"] = review.deliverables_of(conn, engagement_id)
        e["history_count"] = conn.execute("SELECT COUNT(*) FROM history WHERE engagement_id=?", (engagement_id,)).fetchone()[0]
    return e


def _diff(old, new):
    return {k: [old.get(k), new[k]] for k in new if old.get(k) != new[k]}


def save(data):
    """Create (no ``id``) or update (with ``id``) an engagement. ``items`` {kind: [..]} adds items without id and
    updates those with one; it never deletes."""
    data = dict(data or {})
    engagement_id = data.pop("id", None)
    nested = data.pop("items", None) or {}
    if not isinstance(nested, dict):
        raise err("e.items_object")
    with db.connect() as conn:
        if engagement_id:
            old = _row_eng(_require(conn, engagement_id))
            merged = {k: old[k] for k in ENG_FIELDS}
            merged.update(data)
            model = _validate(EngagementIn, merged).model_dump()
            changes = _diff(old, model)
            if changes:
                conn.execute("UPDATE engagements SET name=?,client_name=?,client_ref=?,origin=?,status=?,currency=?,"
                             "budget_min=?,budget_max=?,notes=?,denylist=?,kind=?,updated=? WHERE id=?",
                             (model["name"], model["client_name"], db.dumps(model["client_ref"]) if model["client_ref"] else None,
                              model["origin"], model["status"], model["currency"], model["budget_min"], model["budget_max"],
                              model["notes"], db.dumps(model["denylist"]) if model["denylist"] is not None else None,
                              model["kind"], db.now(), engagement_id))
                db.log(conn, engagement_id, "update", "engagement", engagement_id, "h.eng_updated", {"fields": ", ".join(sorted(changes))}, changes)
        else:
            model = _validate(EngagementIn, data).model_dump()
            engagement_id = db.new_id()
            ts = db.now()
            conn.execute("INSERT INTO engagements(id,name,client_name,client_ref,origin,status,currency,budget_min,budget_max,"
                         "notes,denylist,kind,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (engagement_id, model["name"], model["client_name"], db.dumps(model["client_ref"]) if model["client_ref"] else None,
                          model["origin"], model["status"], model["currency"], model["budget_min"], model["budget_max"],
                          model["notes"], db.dumps(model["denylist"]) if model["denylist"] is not None else None, model["kind"], ts, ts))
            db.log(conn, engagement_id, "create", "engagement", engagement_id, "h.eng_created", {"name": model["name"]})
        for kind, entries in nested.items():
            for entry in entries or []:
                _save_item(conn, engagement_id, kind, dict(entry))
    return get(engagement_id)


def delete(engagement_id):
    with db.connect() as conn:
        _require(conn, engagement_id)
        conn.execute("DELETE FROM engagements WHERE id=?", (engagement_id,))
        conn.execute("DELETE FROM history WHERE engagement_id=?", (engagement_id,))
        conn.execute("DELETE FROM settings WHERE key=?", ("synonyms:" + engagement_id,))
    return {"deleted": engagement_id}


def _title(kind, body):
    return body.get("title") or body.get("what") or body.get("text") or kind


def _save_item(conn, engagement_id, kind, data):
    if kind not in ITEM_MODELS:
        raise err("e.unknown_kind", kind=kind, kinds=", ".join(ITEM_KINDS))
    _require(conn, engagement_id)
    item_id = data.pop("id", None)
    own_kind = "kind" in ITEM_MODELS[kind].model_fields  # payments and materials have a "kind" of their own (invoice / atlas...)
    for noise in (("created", "updated") if own_kind else ("kind", "created", "updated")):
        data.pop(noise, None)
    if item_id:
        row = conn.execute("SELECT * FROM items WHERE id=? AND engagement_id=?", (item_id, engagement_id)).fetchone()
        if not row or row["kind"] != kind:
            raise not_found("e.not_found_item", kind=texts.tr("kind." + kind), id=item_id)
        old = db.loads(row["body"])
        body = _validate(ITEM_MODELS[kind], {**old, **data}).model_dump()
        changes = _diff(old, body)
        if changes:
            conn.execute("UPDATE items SET body=?,updated=? WHERE id=?", (db.dumps(body), db.now(), item_id))
            conn.execute("UPDATE engagements SET updated=? WHERE id=?", (db.now(), engagement_id))
            db.log(conn, engagement_id, "update", kind, item_id, "h.item_updated", {"kind": kind, "title": _title(kind, body)}, changes)
    else:
        body = _validate(ITEM_MODELS[kind], data).model_dump()
        item_id = db.new_id()
        seq = conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM items WHERE engagement_id=?", (engagement_id,)).fetchone()[0]
        ts = db.now()
        conn.execute("INSERT INTO items(id,engagement_id,kind,body,seq,created,updated) VALUES(?,?,?,?,?,?,?)",
                     (item_id, engagement_id, kind, db.dumps(body), seq, ts, ts))
        conn.execute("UPDATE engagements SET updated=? WHERE id=?", (ts, engagement_id))
        db.log(conn, engagement_id, "create", kind, item_id, "h.item_added", {"kind": kind, "title": _title(kind, body)}, body)
    return item_id


def save_item(engagement_id, kind, data):
    with db.connect() as conn:
        item_id = _save_item(conn, engagement_id, kind, dict(data or {}))
        row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    return {"id": item_id, "kind": kind, **db.loads(row["body"])}


def delete_item(engagement_id, item_id):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM items WHERE id=? AND engagement_id=?", (item_id, engagement_id)).fetchone()
        if not row:
            raise not_found("e.not_found_item2", id=item_id)
        body = db.loads(row["body"])
        conn.execute("DELETE FROM items WHERE id=?", (item_id,))
        conn.execute("UPDATE engagements SET updated=? WHERE id=?", (db.now(), engagement_id))
        db.log(conn, engagement_id, "delete", row["kind"], item_id, "h.item_removed", {"kind": row["kind"], "title": _title(row["kind"], body)}, body)
    return {"deleted": item_id}


@texts.localized
def history(engagement_id, limit=200):
    with db.connect() as conn:
        _require(conn, engagement_id)
        rows = conn.execute("SELECT * FROM history WHERE engagement_id=? ORDER BY id DESC LIMIT ?", (engagement_id, limit)).fetchall()
    return [{"id": r["id"], "ts": r["ts"], "action": r["action"], "entity": r["entity"], "entity_id": r["entity_id"],
             "summary": db.render_msg(*_msg(r)) if r["msg"] else r["summary"], "changes": db.loads(r["changes"])} for r in rows]


def _msg(row):
    m = db.loads(row["msg"])
    return m["key"], m["params"], texts.cur()


# ---- settings (deny-list shared by every engagement unless the engagement has its own; effort bands used by every
# scope comparison unless the call passes its own)
def get_settings():
    with db.connect() as conn:
        rows = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings WHERE key IN ('denylist', 'bands', 'synonyms')")}
    saved = db.loads(rows["bands"]) if "bands" in rows else {}
    return {"denylist": db.loads(rows["denylist"]) if "denylist" in rows else list(DEFAULT_DENYLIST), "default_denylist": DEFAULT_DENYLIST,
            "bands": scope.merge_bands(saved), "bands_custom": saved, "default_bands": scope.merge_bands(),
            "synonyms": db.loads(rows["synonyms"]) if "synonyms" in rows else []}


def set_settings(data):
    """Replace the deny-list and/or change the effort bands: the parts given override the saved ones; ``bands: {}`` (or
    null) goes back to the default bands."""
    if not isinstance(data, dict) or ("denylist" not in data and "bands" not in data and "synonyms" not in data):
        raise err("e.settings_keys")
    synonyms = scope.validate_synonyms(data["synonyms"]) if "synonyms" in data else None
    words = None
    if "denylist" in data:
        words = data["denylist"]
        if not isinstance(words, list) or not all(isinstance(w, str) for w in words):
            raise err("e.denylist_list")
        words = [w.strip() for w in words if w.strip()]
    bands = None
    if data.get("bands"):
        bands = get_settings()["bands_custom"]
        for fam, parts in scope.validate_bands(data["bands"]).items():
            bands.setdefault(fam, {}).update(parts)
    with db.connect() as conn:
        if words is not None:
            conn.execute("INSERT INTO settings(key,value) VALUES('denylist',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (db.dumps(words),))
        if "bands" in data:
            if bands:
                conn.execute("INSERT INTO settings(key,value) VALUES('bands',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                             (db.dumps(bands),))
            else:
                conn.execute("DELETE FROM settings WHERE key='bands'")
        if synonyms is not None:
            _store_synonyms(conn, "synonyms", synonyms)
    return get_settings()


# ---- synonyms for scope matching: one list for every engagement (settings) plus one per engagement
def _store_synonyms(conn, key, groups):
    if groups:
        conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, db.dumps(groups)))
    else:
        conn.execute("DELETE FROM settings WHERE key=?", (key,))


def get_synonyms(engagement_id):
    """The groups used when comparing this engagement's scope: its own, then the shared ones."""
    with db.connect() as conn:
        _require(conn, engagement_id)
        row = conn.execute("SELECT value FROM settings WHERE key=?", ("synonyms:" + engagement_id,)).fetchone()
    own = db.loads(row["value"]) if row else []
    shared = get_settings()["synonyms"]
    return {"engagement_id": engagement_id, "groups": own, "shared": shared, "in_use": own + [g for g in shared if g not in own]}


def set_synonyms(engagement_id, groups):
    """Replace this engagement's synonym groups (``[]`` clears them)."""
    groups = scope.validate_synonyms(groups)
    with db.connect() as conn:
        _require(conn, engagement_id)
        _store_synonyms(conn, "synonyms:" + engagement_id, groups)
        db.log(conn, engagement_id, "update", "synonyms", engagement_id, "h.synonyms", {"n": len(groups)}, {"groups": groups})
    return get_synonyms(engagement_id)
