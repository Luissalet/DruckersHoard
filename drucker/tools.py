"""One tool catalogue for MCP and HTTP (``/api/agent/call``). Names carry the ``drucker_`` prefix."""
from __future__ import annotations

from . import engagements, examples, package, proposal, review, scope
from .errors import DruckerError


def f(kind="string", **extra):
    return {"type": kind, **extra}


OBJ = f("object")
EID = {"engagement_id": f(description="Engagement id")}
DID = {"deliverable_id": f(description="Deliverable id")}
from .models import ITEM_KINDS as _K
ITEM_KINDS = list(_K)
PKG = {**DID, "version": f(description="Version number (1, 2...) or version id"),
       "spec": f("object", description="{editable_files, exports, data_sources:[{name,authorised}], instructions, examples, limitations}")}


def _scope_compare(a):
    a = dict(a)
    eid = a.pop("engagement_id", None)
    if eid:
        e = engagements.get(eid)
        sc = e["items"]["scope"]
        a.setdefault("initial", [i["title"] for i in sc if i["origin"] == "initial"] or None)
        a.setdefault("agreement", [i["title"] for i in sc if i["status"] in ("agreed", "done")] or None)
        ctx = {"deliverables": [d["name"] for d in e["deliverables"]],
               "milestones": [{"title": m["title"], "status": m["status"]} for m in e["items"]["milestone"]]}
        a["context"] = {**ctx, **(a.get("context") or {})}
    return scope.compare(a.get("initial"), a.get("agreement"), a.get("request"), a.get("request_mode", "delta"),
                         a.get("context"), a.get("bands"), a.get("hourly_rate"))


def _review(a):
    if a.get("deliverable_id"):
        return review.desk(a["deliverable_id"])
    if a.get("engagement_id"):
        e = engagements.get(a["engagement_id"])
        return {"engagement_id": e["id"], "desks": [review.desk(d["id"]) for d in e["deliverables"]]}
    raise DruckerError("Give deliverable_id or engagement_id")


def _settings(a):
    return engagements.set_settings(a) if "denylist" in a else engagements.get_settings()


# name, description, properties, required, read-only, destructive, handler
SPECS = [
    ("drucker_engagements", "List engagements (encargos) with client, status and budget range. Optional status and name/client text filter.",
     {"status": f(enum=["lead", "active", "paused", "closed"]), "query": f()}, [], True, False,
     lambda a: engagements.list_engagements(a.get("status"), a.get("query"))),
    ("drucker_engagement_get", "Read one engagement file: client, origin, budget, scope, milestones, materials, decisions, payments, assumptions, questions, deliverables with versions. References to People/Ledger/Atlas stay references.",
     EID, ["engagement_id"], True, False, lambda a: engagements.get(a["engagement_id"])),
    ("drucker_engagement_save", "Create (no id) or update (with id) an engagement. Optional items {kind:[..]} adds items without id and updates those with id; never deletes. Kinds: scope, milestone, material, decision, payment, assumption, question. Payments without a Ledger ref are marked manual. Every change is written to the history.",
     {"id": f(), "name": f(), "client_name": f(), "client_ref": f("object", description="{app:'people', id, label}"), "origin": f(),
      "status": f(enum=["lead", "active", "paused", "closed"]), "currency": f(), "budget_min": f("number"), "budget_max": f("number"),
      "notes": f(), "denylist": f("array", items=f()), "items": f("object", description="{kind: [item, ...]}")}, [], False, False, engagements.save),
    ("drucker_item_save", "Add or update one item of an engagement (scope, milestone, material, decision, payment, assumption, question). Include id inside item to update.",
     {**EID, "kind": f(enum=ITEM_KINDS), "item": OBJ}, ["engagement_id", "kind", "item"], False, False,
     lambda a: engagements.save_item(a["engagement_id"], a["kind"], a["item"])),
    ("drucker_item_delete", "Remove one item from an engagement; the removal stays in the history.",
     {**EID, "item_id": f()}, ["engagement_id", "item_id"], False, True, lambda a: engagements.delete_item(a["engagement_id"], a["item_id"])),
    ("drucker_history", "Timeline of every change in an engagement, newest first, with old and new values.",
     {**EID, "limit": f("integer", minimum=1, maximum=1000)}, ["engagement_id"], True, False,
     lambda a: engagements.history(a["engagement_id"], a.get("limit", 200))),
    ("drucker_scope_compare", "Compare initial request, agreement and a new request (text or items). Classifies each item as added, removed, ambiguous, already_included or unchanged; gives effort as an hours range with the reason (format change vs pipeline rework) and three commercial options: include, change order with range, defer. Deterministic matching; uncertain matches stay ambiguous. With engagement_id it uses the stored scope and deliverables. Money only if hourly_rate {min,max,currency} is given.",
     {"engagement_id": f(), "initial": f(description="text or list of items"), "agreement": f(description="text or list of items"),
      "request": f(description="text or list of items; required"), "request_mode": f(enum=["delta", "full"], description="delta: only new asks; full: whole new scope"),
      "context": OBJ, "bands": OBJ, "hourly_rate": OBJ}, ["request"], True, False, _scope_compare),
    ("drucker_proposal", "Draft a proposal from an engagement (format json, md or html). Each sentence is tagged verified (with its source), assumption or question. md/html are refused while the text contains a deny-listed internal name; json always returns the violations.",
     {**EID, "format": f(enum=["json", "md", "html"]), "lang": f(enum=["es", "en"]), "denylist": f("array", items=f())}, ["engagement_id"], True, False,
     lambda a: proposal.proposal(a["engagement_id"], a.get("format", "json"), a.get("lang", "es"), a.get("denylist"))),
    ("drucker_review", "Review desk: versions with hashes, comments with anchor and status, which comments are stale (a later, different version exists) or addressed, and the single version to deliver. Give deliverable_id for one desk or engagement_id for all.",
     {**DID, **EID}, [], True, False, _review),
    ("drucker_deliverable_save", "Create a deliverable (or rename it with deliverable_id).",
     {**EID, "name": f(), "kind": f(), "deliverable_id": f()}, ["engagement_id", "name"], False, False,
     lambda a: review.save_deliverable(a["engagement_id"], a["name"], a.get("kind", ""), a.get("deliverable_id"))),
    ("drucker_version_add", "Add the next version of a deliverable. file_ref is a local path, URL or Atlas pointer; a local file is hashed (sha256). A declared sha256 that does not match is refused.",
     {**DID, "file_ref": f(description="path | url | {kind, ref, atlas}"), "sha256": f(), "note": f()}, ["deliverable_id", "file_ref"], False, False,
     lambda a: review.add_version(a["deliverable_id"], a["file_ref"], a.get("sha256"), a.get("note", ""))),
    ("drucker_comment_add", "Add feedback anchored to one version, optionally to a page, region, time range or object/cell: anchor {kind: page|region|time|object, value}.",
     {"version_id": f(), "text": f(), "author": f(), "anchor": OBJ}, ["version_id", "text"], False, False,
     lambda a: review.add_comment(a["version_id"], a["text"], a.get("author", ""), a.get("anchor"))),
    ("drucker_comment_status", "Set a comment open, fixed (needs fixed_in: a later version) or wontfix.",
     {"comment_id": f(), "status": f(enum=["open", "fixed", "wontfix"]), "fixed_in": f(description="version number or id")}, ["comment_id", "status"], False, False,
     lambda a: review.set_comment_status(a["comment_id"], a["status"], a.get("fixed_in"))),
    ("drucker_deliver_select", "Mark exactly one version of a deliverable as the one to deliver.",
     {**DID, "version": f()}, ["deliverable_id", "version"], False, False, lambda a: review.set_to_deliver(a["deliverable_id"], a["version"])),
    ("drucker_package_verify", "Check a delivery package without writing anything: files exist, hashes match, exports open (zip/JSON/CSV/PDF/PNG/GLB/STL basic validation), data sources authorised, instructions and limitations present. Returns ready true only if every check passes.",
     PKG, ["deliverable_id", "version"], True, False, lambda a: package.verify_only(a["deliverable_id"], a["version"], a.get("spec"))),
    ("drucker_package", "Assemble the delivery package of a version: verify, then write manifest.json and package.zip in the data folder. Not ready (and no zip) if any check fails. Without spec, the version's own local file is the editable file.",
     PKG, ["deliverable_id", "version"], False, False, lambda a: package.build(a["deliverable_id"], a["version"], a.get("spec"))),
    ("drucker_settings", "Read the client-facing deny-list (internal names that must never appear in proposals); pass denylist to replace it.",
     {"denylist": f("array", items=f())}, [], False, False, _settings),
    ("drucker_example", "Invented sample engagement, scope-comparison input and package spec shape. Read-only; nothing is stored.",
     {}, [], True, False, lambda a: {"engagement": examples.example_engagement(), "scope_compare": examples.example_scope(),
                                      "package_spec": {"editable_files": ["path/source.ext"], "exports": [{"path": "path/out.pdf"}],
                                                       "data_sources": [{"name": "sales.csv", "authorised": True}], "instructions": "How to rebuild...",
                                                       "examples": [], "limitations": ["..."]}}),
]
HANDLERS = {s[0]: s[6] for s in SPECS}


def catalogue():
    return [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": p, "required": r, "additionalProperties": False},
             "annotations": {"readOnlyHint": ro, "destructiveHint": de, "openWorldHint": False}}
            for n, d, p, r, ro, de, _ in SPECS]


def call(name, arguments=None):
    if name not in HANDLERS:
        raise DruckerError(f"Unknown tool {name!r}", status=404)
    args = arguments or {}
    if not isinstance(args, dict):
        raise DruckerError("arguments must be an object")
    spec = next(s for s in SPECS if s[0] == name)
    for req in spec[3]:
        if args.get(req) in (None, ""):
            raise DruckerError(f"{req} is required")
    unknown = set(args) - set(spec[2])
    if unknown:
        raise DruckerError("Unknown argument(s): " + ", ".join(sorted(unknown)))
    return HANDLERS[name](args)
