"""Reproducible delivery package: verify the parts, then write a manifest and a zip. Not ready if any check fails."""
from __future__ import annotations

import csv
import io
import json
import re
import struct
import zipfile
from pathlib import Path

from . import db, review
from .errors import DruckerError, NotFound

FIXED_TIME = (2020, 1, 1, 0, 0, 0)
FORMATS = {".zip": "zip", ".json": "json", ".csv": "csv", ".pdf": "pdf", ".png": "png", ".glb": "glb", ".stl": "stl"}


# ---- basic per-format validation: "does it open / re-import", not "is it good"
def validate_format(path: Path, fmt: str | None = None) -> tuple[bool | None, str]:
    """(True, detail) valid, (False, reason) broken, (None, note) no validator for this format."""
    fmt = fmt or FORMATS.get(path.suffix.lower())
    try:
        data = path.read_bytes()
    except OSError as error:
        return False, f"cannot read: {error.strerror or error}"
    if fmt is None:
        return None, "no validator for this format; existence and hash only"
    if not data:
        return False, "file is empty"
    try:
        if fmt == "zip":
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                bad = z.testzip()
                if bad:
                    return False, f"corrupt member {bad}"
                return (True, f"{len(z.namelist())} member(s)") if z.namelist() else (False, "zip has no members")
        if fmt == "json":
            json.loads(data.decode("utf-8-sig"))
            return True, "parses as JSON"
        if fmt == "csv":
            rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
            if len(rows) < 1 or not rows[0]:
                return False, "no header row"
            width = len(rows[0])
            if any(len(r) != width for r in rows if r):
                return False, "rows with a different number of columns than the header"
            return True, f"{len(rows) - 1} data row(s), {width} column(s)"
        if fmt == "pdf":
            if not data.startswith(b"%PDF-"):
                return False, "missing %PDF- header"
            return (True, "PDF header and end marker found") if b"%%EOF" in data[-2048:] else (False, "missing %%EOF end marker (truncated?)")
        if fmt == "png":
            if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
                return False, "not a PNG (signature/IHDR)"
            w, h = struct.unpack(">II", data[16:24])
            if not (w and h):
                return False, "zero dimensions"
            return (True, f"{w}x{h}") if data[-12:-8] == b"\x00\x00\x00\x00" and data[-8:-4] == b"IEND" else (False, "missing IEND (truncated?)")
        if fmt == "glb":
            if data[:4] != b"glTF" or len(data) < 20:
                return False, "not a GLB (magic)"
            version, length = struct.unpack("<II", data[4:12])
            if version != 2 or length != len(data):
                return False, f"GLB header says version {version}, {length} bytes; file has {len(data)}"
            clen, ctype = struct.unpack("<II", data[12:20])
            if ctype != 0x4E4F534A:
                return False, "first chunk is not JSON"
            json.loads(data[20:20 + clen].decode("utf-8"))
            return True, "GLB 2.0, JSON chunk parses"
        if fmt == "stl":
            head = data[:80].lstrip().lower()
            if head.startswith(b"solid") and b"endsolid" in data[-200:].lower() and b"facet" in data:
                return True, "ASCII STL with facets"
            if len(data) >= 84:
                n = struct.unpack("<I", data[80:84])[0]
                if n > 0 and len(data) == 84 + 50 * n:
                    return True, f"binary STL, {n} triangle(s)"
            return False, "neither a complete ASCII STL nor a binary STL with a consistent size"
    except (ValueError, UnicodeDecodeError, zipfile.BadZipFile, struct.error, csv.Error) as error:
        return False, f"does not open as {fmt}: {error}"
    return None, "no validator"


def _entry(raw, role):
    """Normalise one file entry: path string or {path|ref, sha256, format, name}."""
    if isinstance(raw, str):
        raw = {"path": raw}
    if not isinstance(raw, dict):
        raise DruckerError(f"{role}: each file is a path or an object {{path, sha256?, format?}}")
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
    _check(checks, "has_editable", "At least one editable file", bool(spec.get("editable_files")),
           "" if spec.get("editable_files") else "Add the source/editable files so the work can be reproduced.")
    for role, raws in groups:
        for raw in raws:
            f = _entry(raw, role)
            label = f"{role}: {f['ref'] or '(empty)'}"
            path = Path(f["ref"]).expanduser() if f["ref"] and not f["ref"].lower().startswith(("http://", "https://")) else None
            if path is None:
                _check(checks, f"file:{role}:{f['ref']}", label, False, "Not a local file: cannot verify existence or hash. Give a local path.")
                files.append({**f, "size": None, "actual_sha256": None})
                continue
            if not path.is_file():
                _check(checks, f"file:{role}:{f['ref']}", label, False, "File not found.")
                files.append({**f, "size": None, "actual_sha256": None})
                continue
            digest = review.sha256_file(path)
            files.append({**f, "size": path.stat().st_size, "actual_sha256": digest, "path": path})
            _check(checks, f"file:{role}:{f['ref']}", label, True, "File exists.")
            if f["sha256"]:
                _check(checks, f"hash:{role}:{f['ref']}", f"hash: {path.name}", f["sha256"] == digest,
                       "Hash matches." if f["sha256"] == digest else f"Declared {f['sha256'][:12]}..., file is {digest[:12]}...")
            if role in ("export", "editable", "example"):
                ok, detail = validate_format(path, f["format"])
                if ok is not None:
                    _check(checks, f"format:{role}:{f['ref']}", f"opens: {path.name}", ok, detail)
    if version_info and version_info.get("sha256") and version_info.get("path"):
        p = Path(version_info["path"])
        actual = review.sha256_file(p) if p.is_file() else None
        _check(checks, "version_hash", f"Version file matches recorded hash ({p.name})", actual == version_info["sha256"],
               "Recorded hash matches." if actual == version_info["sha256"] else "The file changed after the version was recorded, or is missing.")
    sources = spec.get("data_sources") or []
    for s in sources:
        name = (s.get("name") if isinstance(s, dict) else None) or ""
        ok = bool(name) and isinstance(s, dict) and s.get("authorised") is True
        _check(checks, f"source:{name}", f"Data source: {name or '(no name)'}", ok,
               "Authorised." if ok else "Not authorised (set authorised: true only once the owner of the data has agreed).")
    instr = spec.get("instructions")
    text = instr.get("text") if isinstance(instr, dict) else instr if isinstance(instr, str) else ""
    ipath = instr.get("path") if isinstance(instr, dict) else None
    if not text and ipath:
        p = Path(ipath).expanduser()
        text = p.read_text(encoding="utf-8-sig", errors="replace") if p.is_file() else ""
    _check(checks, "instructions", "Instructions present", bool((text or "").strip()), "" if (text or "").strip() else "Write how to open, rebuild and use the files.")
    limits = [l.strip() for l in (spec.get("limitations") or []) if isinstance(l, str) and l.strip()]
    _check(checks, "limitations", "Limitations declared", bool(limits), "" if limits else "State the real limitations (write \"none known\" only if true).")
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


def build(deliverable_id, version, spec, build_zip=True):
    """Verify and, if everything passes, write manifest.json and package.zip under ``<data>/packages``. A package that
    fails any check is recorded as not ready and no zip is written."""
    with db.connect() as conn:
        d = conn.execute("SELECT * FROM deliverables WHERE id=?", (deliverable_id,)).fetchone()
        if not d:
            raise NotFound(f"Deliverable {deliverable_id!r} not found")
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
            result["checks"].append({"id": "zip_roundtrip", "label": "Zip re-opens and matches the manifest", "ok": False, "detail": problem})
        else:
            (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            result["checks"].append({"id": "zip_roundtrip", "label": "Zip re-opens and matches the manifest", "ok": True, "detail": ""})
    pid = None
    if build_zip:  # verifying alone leaves no trace
        pid = db.new_id()
        with db.connect() as conn:
            conn.execute("INSERT INTO packages(id,version_id,ready,manifest,zip_path,created) VALUES(?,?,?,?,?,?)",
                         (pid, v["id"], int(result["ready"]), db.dumps(manifest), str(zip_path) if zip_path else None, db.now()))
            db.log(conn, d["engagement_id"], "create", "package", pid,
                   f"{d['name']} v{v['n']}: package {'ready' if result['ready'] else 'not ready'}",
                   {"failed": [c["id"] for c in result["checks"] if not c["ok"]]})
    return {"id": pid, "ready": result["ready"], "checks": result["checks"], "manifest": manifest,
            "zip_path": str(zip_path) if zip_path else None,
            "failed": [c for c in result["checks"] if not c["ok"]]}


def verify_only(deliverable_id, version, spec):
    return build(deliverable_id, version, spec, build_zip=False)


def _write_zip(zip_path, result, manifest):
    by_src = {(f["role"], f["ref"]): f for f in result["files"] if f.get("actual_sha256")}
    members = {e["arcname"]: Path(by_src[(e["role"], e["source_path"])]["path"]).read_bytes() for e in manifest["files"]}
    members["INSTRUCTIONS.md"] = (result["instructions_text"] + "\n").encode("utf-8")
    members["LIMITATIONS.md"] = ("# Limitations\n\n" + "\n".join(f"- {l}" for l in result["limitations"]) + "\n").encode("utf-8")
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
                return "zip is corrupt"
            for e in manifest["files"]:
                if hashlib.sha256(z.read(e["arcname"])).hexdigest() != e["sha256"]:
                    return f"{e['arcname']} differs from the manifest"
            for needed in ("manifest.json", "INSTRUCTIONS.md", "LIMITATIONS.md"):
                if needed not in z.namelist():
                    return f"{needed} missing"
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        return str(error)
    return ""
