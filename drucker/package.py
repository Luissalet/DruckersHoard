"""Reproducible delivery package: verify the parts, then write a manifest and a zip. Not ready if any check fails."""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

from . import db, links, review, texts
from .errors import err, not_found
from .formats import FORMATS, validate_format  # noqa: F401 - validate_format stays importable from here

FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def _entry(raw, role):
    """Normalise one file entry: path string or {path|ref, sha256, format, name}."""
    if isinstance(raw, str):
        raw = {"path": raw}
    if not isinstance(raw, dict):
        raise err("e.entry", role=role)
    ref = raw.get("path") or raw.get("ref")
    if isinstance(ref, dict):
        ref = ref.get("ref")
    ref = str(ref or "").strip()
    pointer = links.atlas_id(raw) if raw.get("atlas") not in (None, "", {}) else ""
    if not pointer and re.match(r"^(hoard://atlas/|atlas:)", ref, re.I):
        pointer, ref = links.ident(ref), ""
    if pointer and not ref:
        ref = "hoard://atlas/file/" + pointer
    return {"role": role, "ref": ref, "sha256": (raw.get("sha256") or "").lower() or None, "format": raw.get("format"),
            "name": raw.get("name"), "atlas": pointer or None}


def _via_atlas(f, checks):
    """Ask Atlas for the current path and hash of a pointer. On success the entry points at the live local path; otherwise the
    recorded local path is used when there is one (the pointer is then reported as unverified) or the entry fails."""
    live = links.atlas_file(f["atlas"])
    cid, label = f"atlas:{f['role']}:{f['atlas']}", texts.tr("p.atlas", id=f["atlas"])
    if live["state"] == "ok":
        _check(checks, cid, label, True, texts.tr("p.atlas_ok", path=live["path"], rev=(live["sha256"] or "?")[:12]))
        f.update(ref=live["path"], atlas_sha=live["sha256"])
        return True
    recorded = Path(f["ref"]).expanduser() if f["ref"] and not f["ref"].lower().startswith(("http://", "https://", "hoard://")) else None
    if live["state"] == "unavailable" and recorded is not None and recorded.is_file():
        _check(checks, cid, label, True, texts.tr("p.atlas_unverified", path=str(recorded)))
        return True
    _check(checks, cid, label, False, texts.tr("p.atlas_" + live["state"]) + (f" {live['detail']}" if live.get("detail") else ""))
    return False


def _check(checks, cid, label, ok, detail=""):
    checks.append({"id": cid, "label": label, "ok": ok, "detail": detail})
    return ok


def _glb_official(checks, role, ref, path):
    """The Khronos validator, asked of Vulcan through the hub. It adds a check only when Vulcan answers: errors fail the package,
    warnings do not. Without Vulcan the structural check above is all there is and the detail of that check says so."""
    r = links.gltf_check(path)
    if r["state"] == "unavailable":
        for c in reversed(checks):
            if c["id"] == f"format:{role}:{ref}":
                c["detail"] += " " + texts.tr("p.glb_structural")
                break
        return
    if r["state"] == "ok":
        _check(checks, f"glb_khronos:{role}:{ref}", texts.tr("p.glb_khronos", name=path.name), True,
               texts.tr("p.glb_khronos_ok", w=r.get("warnings", 0)))
    else:
        _check(checks, f"glb_khronos:{role}:{ref}", texts.tr("p.glb_khronos", name=path.name), False,
               texts.tr("p.glb_khronos_bad", e=r.get("errors", 0), w=r.get("warnings", 0)) if r["state"] == "invalid" else (r.get("detail") or r["state"]))


def verify(spec: dict, version_info: dict | None = None) -> dict:
    """Run every check; ``ready`` only when all pass. Returns checks and the file table for the manifest."""
    spec = spec or {}
    checks, files = [], []
    groups = (("editable", spec.get("editable_files") or []), ("export", spec.get("exports") or []), ("example", spec.get("examples") or []))
    _check(checks, "has_editable", texts.tr("p.has_editable"), bool(spec.get("editable_files")),
           "" if spec.get("editable_files") else texts.tr("p.has_editable_d"))
    for role, raws in groups:
        for raw in raws:
            f = _entry(raw, role)
            label = f"{texts.tr('p.role.' + role)}: {f['ref'] or texts.tr('p.empty')}"
            if f["atlas"] and not _via_atlas(f, checks):
                files.append({**f, "size": None, "actual_sha256": None})
                continue
            path = Path(f["ref"]).expanduser() if f["ref"] and not f["ref"].lower().startswith(("http://", "https://", "hoard://")) else None
            if path is None:
                _check(checks, f"file:{role}:{f['ref']}", label, False, texts.tr("p.not_local"))
                files.append({**f, "size": None, "actual_sha256": None})
                continue
            if not path.is_file():
                _check(checks, f"file:{role}:{f['ref']}", label, False, texts.tr("p.not_found"))
                files.append({**f, "size": None, "actual_sha256": None})
                continue
            digest = review.sha256_file(path)
            files.append({**f, "size": path.stat().st_size, "actual_sha256": digest, "path": path})
            _check(checks, f"file:{role}:{f['ref']}", label, True, texts.tr("p.exists"))
            if f.get("atlas_sha") and f["atlas_sha"] != digest:
                _check(checks, f"atlas_rev:{role}:{f['atlas']}", texts.tr("p.atlas_rev", name=path.name), False,
                       texts.tr("p.atlas_rev_bad", a=f["atlas_sha"][:12], b=digest[:12]))
            if f["sha256"]:
                _check(checks, f"hash:{role}:{f['ref']}", texts.tr("p.hash", name=path.name), f["sha256"] == digest,
                       texts.tr("p.hash_ok") if f["sha256"] == digest else texts.tr("p.hash_bad", a=f["sha256"][:12], b=digest[:12]))
            if role in ("export", "editable", "example"):
                ok, detail = validate_format(path, f["format"])
                if ok is not None:
                    _check(checks, f"format:{role}:{f['ref']}", texts.tr("p.opens", name=path.name), ok, detail)
                if ok and (f["format"] or FORMATS.get(path.suffix.lower())) == "glb":
                    _glb_official(checks, role, f["ref"], path)
    if version_info and version_info.get("sha256") and version_info.get("path"):
        p = Path(version_info["path"])
        actual = review.sha256_file(p) if p.is_file() else None
        _check(checks, "version_hash", texts.tr("p.version_hash", name=p.name), actual == version_info["sha256"],
               texts.tr("p.version_hash_ok") if actual == version_info["sha256"] else texts.tr("p.version_hash_bad"))
    sources = spec.get("data_sources") or []
    for s in sources:
        name = (s.get("name") if isinstance(s, dict) else None) or ""
        ok = bool(name) and isinstance(s, dict) and s.get("authorised") is True
        _check(checks, f"source:{name}", texts.tr("p.source", name=name or texts.tr("p.no_name")), ok,
               texts.tr("p.source_ok") if ok else texts.tr("p.source_bad"))
    instr = spec.get("instructions")
    text = instr.get("text") if isinstance(instr, dict) else instr if isinstance(instr, str) else ""
    ipath = instr.get("path") if isinstance(instr, dict) else None
    if not text and ipath:
        p = Path(ipath).expanduser()
        text = p.read_text(encoding="utf-8-sig", errors="replace") if p.is_file() else ""
    _check(checks, "instructions", texts.tr("p.instr"), bool((text or "").strip()), "" if (text or "").strip() else texts.tr("p.instr_d"))
    limits = [l.strip() for l in (spec.get("limitations") or []) if isinstance(l, str) and l.strip()]
    _check(checks, "limitations", texts.tr("p.limits"), bool(limits), "" if limits else texts.tr("p.limits_d"))
    return {"ready": all(c["ok"] for c in checks), "checks": checks, "files": files, "instructions_text": (text or "").strip(),
            "limitations": limits, "data_sources": [s for s in sources if isinstance(s, dict)]}


def _slug(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "item"


def _manifest(result, ctx):
    entries = []
    taken = set()
    for f in sorted((x for x in result["files"] if x.get("actual_sha256")), key=lambda x: (x["role"], x["ref"])):
        base = f.get("name") or Path(f["ref"]).name
        arc = f"{f['role']}s/{base}" if f["role"] != "example" else f"examples/{base}"
        n = 1
        while arc in taken:
            n += 1
            arc = f"{f['role']}s/{n}-{base}" if f["role"] != "example" else f"examples/{n}-{base}"
        taken.add(arc)
        entry = {"role": f["role"], "name": base, "arcname": arc, "size": f["size"], "sha256": f["actual_sha256"],
                 "format": f["format"] or FORMATS.get(Path(f["ref"]).suffix.lower()), "source_path": f["ref"]}
        if f.get("atlas"):
            entry["atlas"] = f["atlas"]
        entries.append(entry)
    return {"schema": 1, **ctx, "files": entries, "data_sources": result["data_sources"], "instructions": "INSTRUCTIONS.md",
            "limitations": result["limitations"], "checks": [{"id": c["id"], "ok": c["ok"]} for c in result["checks"]], "ready": result["ready"]}


@texts.localized
def build(deliverable_id, version, spec, build_zip=True):
    """Verify and, if everything passes, write manifest.json and package.zip under ``<data>/packages``. A package that
    fails any check is recorded as not ready and no zip is written."""
    with db.connect() as conn:
        d = conn.execute("SELECT * FROM deliverables WHERE id=?", (deliverable_id,)).fetchone()
        if not d:
            raise not_found("e.not_found_del", id=deliverable_id)
        v = review._resolve_version(conn, deliverable_id, version)
        eng = conn.execute("SELECT name FROM engagements WHERE id=?", (d["engagement_id"],)).fetchone()
    spec = dict(spec or {})
    ref = db.loads(v["file_ref"])
    path = review.local_path(ref)
    pointer = links.atlas_id(ref) if ref.get("atlas") else ""
    if not pointer and ref.get("kind") == "atlas" and ref.get("ref") and not re.search(r"[\\/.]", ref["ref"]):
        pointer = links.ident(ref["ref"])
    atlas_check = None
    if pointer:  # the version is an Atlas pointer: its live path and hash decide, the recorded path is only a fallback
        probe = {"role": "editable", "ref": str(path or ""), "atlas": pointer}
        atlas_check = []
        if _via_atlas(probe, atlas_check):
            path = Path(probe["ref"]).expanduser() if probe["ref"] else path
        else:
            path = None
    if not spec.get("editable_files") and path is not None:
        entry = {"path": str(path)}
        if v["sha256"]:
            entry["sha256"] = v["sha256"]
        if pointer:
            entry["atlas"] = pointer
        spec["editable_files"] = [entry]
    result = verify(spec, {"sha256": v["sha256"], "path": str(path)} if path is not None and v["sha256"] else None)
    if atlas_check and not atlas_check[0]["ok"]:
        result["checks"].insert(0, atlas_check[0])
        result["ready"] = False
    ctx = {"engagement": eng["name"], "deliverable": d["name"], "version": v["n"], "version_sha256": v["sha256"]}
    manifest = _manifest(result, ctx)
    zip_path = None
    if result["ready"] and build_zip:
        out = db.data_dir() / "packages" / d["engagement_id"] / f"{_slug(d['name'])}-v{v['n']}"
        out.mkdir(parents=True, exist_ok=True)
        zip_path = out / "package.zip"
        _write_zip(zip_path, result, manifest)
        problem = _verify_zip(zip_path, manifest)
        if problem:
            zip_path.unlink(missing_ok=True)
            zip_path = None
            result["ready"] = manifest["ready"] = False
            result["checks"].append({"id": "zip_roundtrip", "label": texts.tr("p.zip"), "ok": False, "detail": problem})
        else:
            (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            result["checks"].append({"id": "zip_roundtrip", "label": texts.tr("p.zip"), "ok": True, "detail": ""})
    pid = None
    if build_zip:  # verifying alone leaves no trace
        pid = db.new_id()
        with db.connect() as conn:
            conn.execute("INSERT INTO packages(id,version_id,ready,manifest,zip_path,created) VALUES(?,?,?,?,?,?)",
                         (pid, v["id"], int(result["ready"]), db.dumps(manifest), str(zip_path) if zip_path else None, db.now()))
            db.log(conn, d["engagement_id"], "create", "package", pid,
                   "h.pkg_ready" if result["ready"] else "h.pkg_not_ready", {"name": d["name"], "n": v["n"]},
                   {"failed": [c["id"] for c in result["checks"] if not c["ok"]]})
    return {"id": pid, "ready": result["ready"], "checks": result["checks"], "manifest": manifest,
            "zip_path": str(zip_path) if zip_path else None,
            "failed": [c for c in result["checks"] if not c["ok"]]}


@texts.localized
def verify_only(deliverable_id, version, spec):
    return build(deliverable_id, version, spec, build_zip=False)


def _write_zip(zip_path, result, manifest):
    by_src = {(f["role"], f["ref"]): f for f in result["files"] if f.get("actual_sha256")}
    members = {e["arcname"]: Path(by_src[(e["role"], e["source_path"])]["path"]).read_bytes() for e in manifest["files"]}
    members["INSTRUCTIONS.md"] = (result["instructions_text"] + "\n").encode("utf-8")
    members["LIMITATIONS.md"] = (f"# {texts.tr('p.limitations_title')}\n\n" + "\n".join(f"- {l}" for l in result["limitations"]) + "\n").encode("utf-8")
    members["data-sources.json"] = json.dumps(result["data_sources"], ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    members["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, FIXED_TIME)  # fixed timestamps: same inputs, same bytes
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, members[name])


def _verify_zip(zip_path, manifest):
    import hashlib
    try:
        with zipfile.ZipFile(zip_path) as z:
            if z.testzip():
                return texts.tr("p.zip_corrupt")
            for e in manifest["files"]:
                if hashlib.sha256(z.read(e["arcname"])).hexdigest() != e["sha256"]:
                    return texts.tr("p.zip_differs", name=e["arcname"])
            for needed in ("manifest.json", "INSTRUCTIONS.md", "LIMITATIONS.md"):
                if needed not in z.namelist():
                    return texts.tr("p.zip_missing", name=needed)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        return str(error)
    return ""
