"""Reproducible delivery package: verify the parts, then write a manifest and a zip. Not ready if any check fails."""
from __future__ import annotations

import csv
import io
import json
import re
import struct
import zipfile
from pathlib import Path

from . import db, review, texts
from .errors import err, not_found

FIXED_TIME = (2020, 1, 1, 0, 0, 0)
FORMATS = {".zip": "zip", ".json": "json", ".csv": "csv", ".pdf": "pdf", ".png": "png", ".glb": "glb", ".stl": "stl"}


# ---- basic per-format validation: "does it open / re-import", not "is it good"
def validate_format(path: Path, fmt: str | None = None) -> tuple[bool | None, str]:
    """(True, detail) valid, (False, reason) broken, (None, note) no validator for this format."""
    fmt = fmt or FORMATS.get(path.suffix.lower())
    try:
        data = path.read_bytes()
    except OSError as error:
        return False, texts.tr("v.cannot_read", why=error.strerror or error)
    if fmt is None:
        return None, texts.tr("v.no_validator")
    if not data:
        return False, texts.tr("v.empty")
    try:
        if fmt == "zip":
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                bad = z.testzip()
                if bad:
                    return False, texts.tr("v.zip_corrupt", name=bad)
                return (True, texts.tr("v.zip_members", n=len(z.namelist()))) if z.namelist() else (False, texts.tr("v.zip_empty"))
        if fmt == "json":
            json.loads(data.decode("utf-8-sig"))
            return True, texts.tr("v.json_ok")
        if fmt == "csv":
            rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
            if len(rows) < 1 or not rows[0]:
                return False, texts.tr("v.csv_head")
            width = len(rows[0])
            if any(len(r) != width for r in rows if r):
                return False, texts.tr("v.csv_width")
            return True, texts.tr("v.csv_ok", rows=len(rows) - 1, cols=width)
        if fmt == "pdf":
            if not data.startswith(b"%PDF-"):
                return False, texts.tr("v.pdf_head")
            return (True, texts.tr("v.pdf_ok")) if b"%%EOF" in data[-2048:] else (False, texts.tr("v.pdf_trunc"))
        if fmt == "png":
            if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
                return False, texts.tr("v.png_bad")
            w, h = struct.unpack(">II", data[16:24])
            if not (w and h):
                return False, texts.tr("v.png_zero")
            return (True, f"{w}x{h}") if data[-12:-8] == b"\x00\x00\x00\x00" and data[-8:-4] == b"IEND" else (False, texts.tr("v.png_trunc"))
        if fmt == "glb":
            if data[:4] != b"glTF" or len(data) < 20:
                return False, texts.tr("v.glb_magic")
            version, length = struct.unpack("<II", data[4:12])
            if version != 2 or length != len(data):
                return False, texts.tr("v.glb_header", v=version, len=length, size=len(data))
            clen, ctype = struct.unpack("<II", data[12:20])
            if ctype != 0x4E4F534A:
                return False, texts.tr("v.glb_chunk")
            json.loads(data[20:20 + clen].decode("utf-8"))
            return True, texts.tr("v.glb_ok")
        if fmt == "stl":
            head = data[:80].lstrip().lower()
            if head.startswith(b"solid") and b"endsolid" in data[-200:].lower() and b"facet" in data:
                return True, texts.tr("v.stl_ascii")
            if len(data) >= 84:
                n = struct.unpack("<I", data[80:84])[0]
                if n > 0 and len(data) == 84 + 50 * n:
                    return True, texts.tr("v.stl_bin", n=n)
            return False, texts.tr("v.stl_bad")
    except (ValueError, UnicodeDecodeError, zipfile.BadZipFile, struct.error, csv.Error) as error:
        return False, texts.tr("v.open_fail", fmt=fmt, why=error)
    return None, texts.tr("v.no_validator_short")


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
    return {"role": role, "ref": ref, "sha256": (raw.get("sha256") or "").lower() or None, "format": raw.get("format"),
            "name": raw.get("name")}


def _check(checks, cid, label, ok, detail=""):
    checks.append({"id": cid, "label": label, "ok": ok, "detail": detail})
    return ok


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
            path = Path(f["ref"]).expanduser() if f["ref"] and not f["ref"].lower().startswith(("http://", "https://")) else None
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
            if f["sha256"]:
                _check(checks, f"hash:{role}:{f['ref']}", texts.tr("p.hash", name=path.name), f["sha256"] == digest,
                       texts.tr("p.hash_ok") if f["sha256"] == digest else texts.tr("p.hash_bad", a=f["sha256"][:12], b=digest[:12]))
            if role in ("export", "editable", "example"):
                ok, detail = validate_format(path, f["format"])
                if ok is not None:
                    _check(checks, f"format:{role}:{f['ref']}", texts.tr("p.opens", name=path.name), ok, detail)
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
        entries.append({"role": f["role"], "name": base, "arcname": arc, "size": f["size"], "sha256": f["actual_sha256"],
                        "format": f["format"] or FORMATS.get(Path(f["ref"]).suffix.lower()), "source_path": f["ref"]})
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
    if not spec.get("editable_files") and path is not None:
        spec["editable_files"] = [{"path": str(path), "sha256": v["sha256"]}] if v["sha256"] else [str(path)]
    result = verify(spec, {"sha256": v["sha256"], "path": str(path)} if path is not None and v["sha256"] else None)
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
