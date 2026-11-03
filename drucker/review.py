"""Deliverable review desk: versions (file ref + hash), anchored comments, correction status and one version to deliver."""
from __future__ import annotations

import hashlib
from pathlib import Path

from . import db
from .errors import DruckerError, NotFound

ANCHOR_KINDS = ("page", "region", "time", "object")
STATUSES = ("open", "fixed", "wontfix")


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_ref(ref) -> dict:
    """A file reference: a path/URL string or {kind: path|url|atlas, ref, atlas?}. Atlas keeps the files; this is a pointer."""
    if isinstance(ref, str):
        ref = {"kind": "url" if ref.lower().startswith(("http://", "https://")) else "path", "ref": ref}
    if not isinstance(ref, dict):
        raise DruckerError("file_ref must be a path, a URL or an object {kind, ref}")
    kind = ref.get("kind") or ("atlas" if ref.get("atlas") else "path")
    if kind not in ("path", "url", "atlas"):
        raise DruckerError("file_ref.kind must be path, url or atlas")
    value = str(ref.get("ref") or "").strip()
    out = {"kind": kind, "ref": value}
    if ref.get("atlas"):
        out["atlas"] = ref["atlas"]
    if not value and not out.get("atlas"):
        raise DruckerError("file_ref.ref is required")
    return out


def local_path(ref) -> Path | None:
    ref = normalize_ref(ref)
    return Path(ref["ref"]).expanduser() if ref["kind"] in ("path", "atlas") and ref["ref"] and not ref["ref"].lower().startswith("http") else None


def _anchor(anchor):
    if anchor in (None, "", {}):
        return None
    if not isinstance(anchor, dict) or anchor.get("kind") not in ANCHOR_KINDS or anchor.get("value") in (None, "", {}, []):
        raise DruckerError("anchor must be {kind: page|region|time|object, value}")
    value = anchor["value"]
    if anchor["kind"] == "time" and isinstance(value, dict):
        s, e = value.get("start"), value.get("end", value.get("start"))
        if not all(isinstance(x, (int, float)) for x in (s, e)) or s > e or s < 0:
            raise DruckerError("time anchor needs numeric start <= end (seconds)")
    return {"kind": anchor["kind"], "value": value}


def _eng_of_deliverable(conn, deliverable_id):
    row = conn.execute("SELECT * FROM deliverables WHERE id=?", (deliverable_id,)).fetchone()
    if not row:
        raise NotFound(f"Deliverable {deliverable_id!r} not found")
    return row


def _version(conn, version_id):
    row = conn.execute("SELECT * FROM versions WHERE id=?", (version_id,)).fetchone()
    if not row:
        raise NotFound(f"Version {version_id!r} not found")
    return row


def _resolve_version(conn, deliverable_id, version):
    """``version`` is a version id or its number within the deliverable."""
    row = conn.execute("SELECT * FROM versions WHERE deliverable_id=? AND (id=? OR n=?)",
                       (deliverable_id, str(version), int(version) if isinstance(version, int) or str(version).isdigit() else -1)).fetchone()
    if not row:
        raise NotFound(f"Version {version!r} not found in this deliverable")
    return row


def _vdict(r):
    return {"id": r["id"], "n": r["n"], "file_ref": db.loads(r["file_ref"]), "sha256": r["sha256"],
            "hash_source": r["hash_source"], "note": r["note"], "created": r["created"]}


def deliverables_of(conn, engagement_id):
    out = []
    for d in conn.execute("SELECT * FROM deliverables WHERE engagement_id=? ORDER BY rowid", (engagement_id,)):
        versions = [_vdict(v) for v in conn.execute("SELECT * FROM versions WHERE deliverable_id=? ORDER BY n", (d["id"],))]
        to = next((v["n"] for v in versions if v["id"] == d["to_deliver_version_id"]), None)
        out.append({"id": d["id"], "name": d["name"], "kind": d["kind"], "versions": versions, "to_deliver": to,
                    "latest": versions[-1]["n"] if versions else None})
    return out


def save_deliverable(engagement_id, name, kind="", deliverable_id=None):
    name = (name or "").strip()
    if not name:
        raise DruckerError("name is required")
    with db.connect() as conn:
        if not conn.execute("SELECT 1 FROM engagements WHERE id=?", (engagement_id,)).fetchone():
            raise NotFound(f"Engagement {engagement_id!r} not found")
        if deliverable_id:
            d = _eng_of_deliverable(conn, deliverable_id)
            conn.execute("UPDATE deliverables SET name=?,kind=? WHERE id=?", (name, kind or d["kind"], deliverable_id))
            db.log(conn, d["engagement_id"], "update", "deliverable", deliverable_id, f"deliverable renamed: {name}")
        else:
            deliverable_id = db.new_id()
            conn.execute("INSERT INTO deliverables(id,engagement_id,name,kind,created) VALUES(?,?,?,?,?)",
                         (deliverable_id, engagement_id, name, kind, db.now()))
            db.log(conn, engagement_id, "create", "deliverable", deliverable_id, f"deliverable added: {name}")
    return desk(deliverable_id)


def add_version(deliverable_id, file_ref, sha256=None, note=""):
    ref = normalize_ref(file_ref)
    if sha256 is not None and not (isinstance(sha256, str) and len(sha256) == 64 and all(c in "0123456789abcdef" for c in sha256.lower())):
        raise DruckerError("sha256 must be 64 hex characters")
    digest, source = (sha256.lower(), "declared") if sha256 else (None, "none")
    path = local_path(ref)
    if path is not None and path.is_file():
        computed = sha256_file(path)
        if digest and digest != computed:
            raise DruckerError("Declared sha256 does not match the file on disk", declared=digest, computed=computed)
        digest, source = computed, "computed"
    with db.connect() as conn:
        d = _eng_of_deliverable(conn, deliverable_id)
        n = conn.execute("SELECT COALESCE(MAX(n),0)+1 FROM versions WHERE deliverable_id=?", (deliverable_id,)).fetchone()[0]
        vid = db.new_id()
        conn.execute("INSERT INTO versions(id,deliverable_id,n,file_ref,sha256,hash_source,note,created) VALUES(?,?,?,?,?,?,?,?)",
                     (vid, deliverable_id, n, db.dumps(ref), digest, source, note or "", db.now()))
        db.log(conn, d["engagement_id"], "create", "version", vid, f"{d['name']}: version {n} added",
               {"file_ref": ref, "sha256": digest, "hash_source": source})
    return desk(deliverable_id)


def add_comment(version_id, text, author="", anchor=None):
    text = (text or "").strip()
    if not text:
        raise DruckerError("text is required")
    anchor = _anchor(anchor)
    with db.connect() as conn:
        v = _version(conn, version_id)
        d = _eng_of_deliverable(conn, v["deliverable_id"])
        cid, ts = db.new_id(), db.now()
        conn.execute("INSERT INTO comments(id,version_id,text,author,anchor,created,updated) VALUES(?,?,?,?,?,?,?)",
                     (cid, version_id, text, author or "", db.dumps(anchor) if anchor else None, ts, ts))
        db.log(conn, d["engagement_id"], "create", "comment", cid, f"{d['name']} v{v['n']}: comment added", {"text": text, "anchor": anchor})
    return desk(v["deliverable_id"])


def set_comment_status(comment_id, status, fixed_in=None):
    if status not in STATUSES:
        raise DruckerError("status must be open, fixed or wontfix")
    with db.connect() as conn:
        c = conn.execute("SELECT * FROM comments WHERE id=?", (comment_id,)).fetchone()
        if not c:
            raise NotFound(f"Comment {comment_id!r} not found")
        v = _version(conn, c["version_id"])
        d = _eng_of_deliverable(conn, v["deliverable_id"])
        fixed_id = None
        if status == "fixed":
            if fixed_in is None:
                raise DruckerError("fixed_in (version number) is required when status is fixed")
            target = _resolve_version(conn, v["deliverable_id"], fixed_in)
            if target["n"] <= v["n"]:
                raise DruckerError("A comment can only be fixed in a later version than the one it is about")
            fixed_id = target["id"]
        conn.execute("UPDATE comments SET status=?,fixed_in_version_id=?,updated=? WHERE id=?", (status, fixed_id, db.now(), comment_id))
        db.log(conn, d["engagement_id"], "update", "comment", comment_id, f"{d['name']} v{v['n']}: comment {status}",
               {"status": [c["status"], status], "fixed_in": fixed_id})
    return desk(v["deliverable_id"])


def set_to_deliver(deliverable_id, version):
    with db.connect() as conn:
        d = _eng_of_deliverable(conn, deliverable_id)
        v = _resolve_version(conn, deliverable_id, version)
        conn.execute("UPDATE deliverables SET to_deliver_version_id=? WHERE id=?", (v["id"], deliverable_id))
        db.log(conn, d["engagement_id"], "update", "deliverable", deliverable_id, f"{d['name']}: version {v['n']} marked to deliver")
    return desk(deliverable_id)


def desk(deliverable_id):
    """The review desk of one deliverable: versions, comments classified as current/stale/addressed, and the version to deliver."""
    with db.connect() as conn:
        d = _eng_of_deliverable(conn, deliverable_id)
        versions = [_vdict(v) for v in conn.execute("SELECT * FROM versions WHERE deliverable_id=? ORDER BY n", (deliverable_id,))]
        by_id = {v["id"]: v for v in versions}
        rows = conn.execute("SELECT c.* FROM comments c JOIN versions v ON v.id=c.version_id WHERE v.deliverable_id=? "
                            "ORDER BY v.n, c.rowid", (deliverable_id,)).fetchall()
    latest = versions[-1]["n"] if versions else None
    comments = []
    for c in rows:
        v = by_id[c["version_id"]]
        later = [w for w in versions if w["n"] > v["n"] and (not v["sha256"] or not w["sha256"] or w["sha256"] != v["sha256"])]
        fixed = by_id.get(c["fixed_in_version_id"])
        item = {"id": c["id"], "version": v["n"], "version_id": v["id"], "text": c["text"], "author": c["author"],
                "anchor": db.loads(c["anchor"]), "status": c["status"], "fixed_in": fixed["n"] if fixed else None,
                "created": c["created"], "stale": False, "addressed_by": fixed["n"] if fixed else None,
                "later_versions": [w["n"] for w in later], "note": ""}
        if c["status"] == "open" and later:
            item["stale"] = True
            span = f"v{later[0]['n']}" if len(later) == 1 else f"v{later[0]['n']} to v{later[-1]['n']}"
            item["note"] = f"About v{v['n']}; {span} {'is newer and differs' if len(later) == 1 else 'are newer and differ'}. Check whether it already addresses this."
        elif c["status"] == "open" and latest is not None and v["n"] < latest:
            item["note"] = f"v{latest} has identical content to v{v['n']}: the feedback still applies."
        elif c["status"] == "fixed":
            item["note"] = f"Fixed in v{fixed['n']}."
        elif c["status"] == "wontfix":
            item["note"] = "Closed as won't fix."
        comments.append(item)
    to = by_id.get(d["to_deliver_version_id"])
    warnings = []
    open_on_target = [c for c in comments if to and c["version"] == to["n"] and c["status"] == "open"]
    if not versions:
        warnings.append("No versions yet.")
    elif not to:
        warnings.append("No version selected to deliver.")
    else:
        if to["n"] != latest:
            warnings.append(f"The version to deliver (v{to['n']}) is not the latest (v{latest}).")
        if open_on_target:
            warnings.append(f"{len(open_on_target)} open comment(s) on v{to['n']}.")
        if any(c["stale"] for c in comments if c["status"] == "open" and c["version"] < to["n"]):
            warnings.append("Open feedback about older versions still needs a decision.")
    return {"id": d["id"], "engagement_id": d["engagement_id"], "name": d["name"], "kind": d["kind"], "versions": versions,
            "latest": latest, "to_deliver": to["n"] if to else None, "to_deliver_version_id": to["id"] if to else None,
            "comments": comments,
            "counts": {s: sum(1 for c in comments if c["status"] == s) for s in STATUSES} | {"stale": sum(1 for c in comments if c["stale"])},
            "ready_to_deliver": bool(to and not open_on_target and to["n"] == latest), "warnings": warnings}
