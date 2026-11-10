"""Structural validation of export files: "does it open and is it coherent", not "is it good".

Each validator reads the bytes and returns ``(True, detail)`` valid, ``(False, reason)`` broken. No third-party parser is used:
ZIP-based Office files are checked through their parts, PDF through its cross-reference chain, GLB through the glTF JSON and
the buffers it points into, MP4 through its box tree."""
from __future__ import annotations

import csv
import io
import json
import re
import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from . import texts

FORMATS = {".zip": "zip", ".json": "json", ".csv": "csv", ".pdf": "pdf", ".png": "png", ".glb": "glb", ".stl": "stl",
           ".docx": "docx", ".xlsx": "xlsx", ".svg": "svg", ".mp4": "mp4", ".m4v": "mp4"}
COMPONENT_BYTES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
TYPE_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _xml(data, what):
    try:
        return ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError(texts.tr("v.xml_bad", what=what, why=error)) from None


# ---- PDF: header, end marker, the startxref chain, a trailer with /Root, a catalog and pages
def _pdf(data):
    if not data.startswith(b"%PDF-"):
        return False, texts.tr("v.pdf_head")
    if b"%%EOF" not in data[-2048:]:
        return False, texts.tr("v.pdf_trunc")
    found = list(re.finditer(rb"startxref\s+(\d+)\s*(?:%%EOF)?", data[-4096:]))
    if not found:
        return False, texts.tr("v.pdf_nostartxref")
    offset = int(found[-1].group(1))
    if offset <= 0 or offset >= len(data):
        return False, texts.tr("v.pdf_xref_off", off=offset)
    at = data[offset:offset + 64].lstrip()
    classic = at.startswith(b"xref")
    stream = re.match(rb"\d+\s+\d+\s+obj", at) is not None
    if not (classic or stream):
        return False, texts.tr("v.pdf_xref_bad", off=offset)
    if classic:
        trailer = re.search(rb"trailer\s*<<(.*?)>>\s*(?:startxref|%%EOF)", data[offset:], re.S)
        head = trailer.group(1) if trailer else b""
        if not trailer:
            return False, texts.tr("v.pdf_trailer")
    else:
        head = data[offset:offset + 2048]
        if not re.search(rb"/Type\s*/XRef", head):
            return False, texts.tr("v.pdf_xref_bad", off=offset)
    if not re.search(rb"/Root\s+\d+\s+\d+\s+R", head):
        return False, texts.tr("v.pdf_root")
    compressed = b"/ObjStm" in data
    pages = len(re.findall(rb"/Type\s*/Page(?![A-Za-z])", data))
    if not compressed:
        if not re.search(rb"/Type\s*/Catalog", data):
            return False, texts.tr("v.pdf_catalog")
        if pages < 1:
            return False, texts.tr("v.pdf_nopages")
        return True, texts.tr("v.pdf_ok2", pages=pages) + (texts.tr("v.pdf_enc") if b"/Encrypt" in head else "")
    return True, texts.tr("v.pdf_ok3") + (texts.tr("v.pdf_enc") if b"/Encrypt" in head else "")


# ---- GLB: header, chunk layout, then the JSON checked against the binary chunk
def _glb(data):
    if data[:4] != b"glTF" or len(data) < 20:
        return False, texts.tr("v.glb_magic")
    version, length = struct.unpack("<II", data[4:12])
    if version != 2 or length != len(data):
        return False, texts.tr("v.glb_header", v=version, len=length, size=len(data))
    chunks, pos = [], 12
    while pos + 8 <= len(data):
        clen, ctype = struct.unpack("<II", data[pos:pos + 8])
        if pos + 8 + clen > len(data):
            return False, texts.tr("v.glb_chunk_over", n=len(chunks) + 1)
        chunks.append((ctype, data[pos + 8:pos + 8 + clen]))
        pos += 8 + clen
    if pos != len(data):
        return False, texts.tr("v.glb_trailing", n=len(data) - pos)
    if not chunks or chunks[0][0] != 0x4E4F534A:
        return False, texts.tr("v.glb_chunk")
    doc = json.loads(chunks[0][1].decode("utf-8"))
    if not isinstance(doc, dict):
        return False, texts.tr("v.glb_chunk")
    if str((doc.get("asset") or {}).get("version", "")) != "2.0":
        return False, texts.tr("v.glb_asset")
    binary = next((c for t, c in chunks[1:] if t == 0x004E4942), None)
    buffers = doc.get("buffers") or []
    views = doc.get("bufferViews") or []
    accessors = doc.get("accessors") or []
    for i, b in enumerate(buffers):
        size = b.get("byteLength", 0)
        if "uri" not in b:
            if i != 0 or binary is None:
                return False, texts.tr("v.glb_nobin", i=i)
            if size > len(binary) or len(binary) - size >= 4:
                return False, texts.tr("v.glb_buflen", i=i, size=size, bin=len(binary))
    for i, v in enumerate(views):
        b = v.get("buffer")
        if not isinstance(b, int) or not 0 <= b < len(buffers):
            return False, texts.tr("v.glb_ref", what=f"bufferViews[{i}].buffer", n=b)
        if v.get("byteOffset", 0) + v.get("byteLength", 0) > buffers[b].get("byteLength", 0):
            return False, texts.tr("v.glb_view_over", i=i)
    for i, a in enumerate(accessors):
        if a.get("componentType") not in COMPONENT_BYTES or a.get("type") not in TYPE_COMPONENTS or not isinstance(a.get("count"), int) or a["count"] < 1:
            return False, texts.tr("v.glb_accessor", i=i)
        if "bufferView" in a:
            vi = a["bufferView"]
            if not isinstance(vi, int) or not 0 <= vi < len(views):
                return False, texts.tr("v.glb_ref", what=f"accessors[{i}].bufferView", n=vi)
            v = views[vi]
            stride = v.get("byteStride") or COMPONENT_BYTES[a["componentType"]] * TYPE_COMPONENTS[a["type"]]
            need = a.get("byteOffset", 0) + stride * (a["count"] - 1) + COMPONENT_BYTES[a["componentType"]] * TYPE_COMPONENTS[a["type"]]
            if need > v.get("byteLength", 0):
                return False, texts.tr("v.glb_acc_over", i=i, need=need, have=v.get("byteLength", 0))
    meshes = doc.get("meshes") or []
    for i, m in enumerate(meshes):
        for prim in m.get("primitives") or []:
            refs = list((prim.get("attributes") or {}).values()) + ([prim["indices"]] if "indices" in prim else [])
            for r in refs:
                if not isinstance(r, int) or not 0 <= r < len(accessors):
                    return False, texts.tr("v.glb_ref", what=f"meshes[{i}] accessor", n=r)
    nodes = doc.get("nodes") or []
    for i, n in enumerate(nodes):
        if "mesh" in n and not (isinstance(n["mesh"], int) and 0 <= n["mesh"] < len(meshes)):
            return False, texts.tr("v.glb_ref", what=f"nodes[{i}].mesh", n=n["mesh"])
        for c in n.get("children") or []:
            if not (isinstance(c, int) and 0 <= c < len(nodes)):
                return False, texts.tr("v.glb_ref", what=f"nodes[{i}].children", n=c)
    scenes = doc.get("scenes") or []
    for i, s in enumerate(scenes):
        for n in s.get("nodes") or []:
            if not (isinstance(n, int) and 0 <= n < len(nodes)):
                return False, texts.tr("v.glb_ref", what=f"scenes[{i}].nodes", n=n)
    if "scene" in doc and not (isinstance(doc["scene"], int) and 0 <= doc["scene"] < len(scenes)):
        return False, texts.tr("v.glb_ref", what="scene", n=doc["scene"])
    for i, im in enumerate(doc.get("images") or []):
        if "bufferView" in im and not (isinstance(im["bufferView"], int) and 0 <= im["bufferView"] < len(views)):
            return False, texts.tr("v.glb_ref", what=f"images[{i}].bufferView", n=im["bufferView"])
    return True, texts.tr("v.glb_ok2", meshes=len(meshes), nodes=len(nodes), accessors=len(accessors), kb=max(1, len(data) // 1024))


# ---- DOCX / XLSX: a zip whose parts exist and parse
def _office(data, kind):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        bad = z.testzip()
        if bad:
            return False, texts.tr("v.zip_corrupt", name=bad)
        names = set(z.namelist())
        main = "word/document.xml" if kind == "docx" else "xl/workbook.xml"
        for need in ("[Content_Types].xml", "_rels/.rels", main):
            if need not in names:
                return False, texts.tr("v.office_part", part=need)
        _xml(z.read("[Content_Types].xml"), "[Content_Types].xml")
        root = _xml(z.read(main), main)
        if kind == "docx":
            paragraphs = [p for p in root.iter() if _local(p.tag) == "p"]
            words = sum(len("".join(t.text or "" for t in p.iter() if _local(t.tag) == "t").split()) for p in paragraphs)
            return True, texts.tr("v.docx_ok", paragraphs=len(paragraphs), words=words)
        sheets = [s for s in root.iter() if _local(s.tag) == "sheet"]
        if not sheets:
            return False, texts.tr("v.xlsx_nosheet")
        rels = {}
        if "xl/_rels/workbook.xml.rels" in names:
            for r in _xml(z.read("xl/_rels/workbook.xml.rels"), "workbook.xml.rels"):
                rels[r.get("Id")] = r.get("Target") or ""
        for s in sheets:
            rid = next((v for k, v in s.attrib.items() if _local(k) == "id"), None)
            target = rels.get(rid)
            if not target:
                return False, texts.tr("v.xlsx_rel", name=s.get("name", "?"))
            part = target.lstrip("/") if target.startswith("/") else "xl/" + target
            if part not in names:
                return False, texts.tr("v.xlsx_part", name=s.get("name", "?"), part=part)
            _xml(z.read(part), part)
        return True, texts.tr("v.xlsx_ok", n=len(sheets), names=", ".join(s.get("name", "?") for s in sheets[:6]))


def _svg(data):
    root = _xml(data, "SVG")
    if _local(root.tag) != "svg":
        return False, texts.tr("v.svg_root", tag=_local(root.tag))
    box = root.get("viewBox")
    size = f"{root.get('width')}x{root.get('height')}" if root.get("width") and root.get("height") else ""
    if box:
        parts = re.split(r"[\s,]+", box.strip())
        try:
            if len(parts) != 4 or float(parts[2]) <= 0 or float(parts[3]) <= 0:
                raise ValueError
        except ValueError:
            return False, texts.tr("v.svg_viewbox", v=box)
        size = size or f"viewBox {box}"
    if not size:
        return False, texts.tr("v.svg_nosize")
    return True, texts.tr("v.svg_ok", size=size, n=sum(1 for _ in root.iter()))


# ---- MP4: the box tree has to add up to the file, with ftyp first, a moov and media data
def _boxes(data, start, end):
    pos = start
    while pos + 8 <= end:
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        head = 8
        if size == 1:
            if pos + 16 > end:
                raise ValueError(texts.tr("v.mp4_box", kind=kind.decode("latin-1")))
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            head = 16
        elif size == 0:
            size = end - pos
        if size < head or pos + size > end:
            raise ValueError(texts.tr("v.mp4_box", kind=kind.decode("latin-1")))
        yield kind.decode("latin-1"), pos + head, pos + size
        pos += size
    if pos != end:
        raise ValueError(texts.tr("v.mp4_trailing", n=end - pos))


def _mp4(data):
    top = list(_boxes(data, 0, len(data)))
    if not top or top[0][0] != "ftyp":
        return False, texts.tr("v.mp4_ftyp")
    kinds = [k for k, _, _ in top]
    if "moov" not in kinds:
        return False, texts.tr("v.mp4_nomoov")
    if "mdat" not in kinds:
        return False, texts.tr("v.mp4_nomdat")
    _, ms, me = next(b for b in top if b[0] == "moov")
    duration, tracks = None, []
    for kind, s, e in _boxes(data, ms, me):
        if kind == "mvhd" and e - s >= 20:
            v = data[s]
            if v == 1 and e - s >= 32:
                scale, dur = struct.unpack(">IQ", data[s + 20:s + 32])
            else:
                scale, dur = struct.unpack(">II", data[s + 12:s + 20])
            duration = dur / scale if scale else None
        elif kind == "trak":
            for k2, s2, e2 in _boxes(data, s, e):
                if k2 == "mdia":
                    for k3, s3, e3 in _boxes(data, s2, e2):
                        if k3 == "hdlr" and e3 - s3 >= 12:
                            tracks.append(data[s3 + 8:s3 + 12].decode("latin-1"))
    if not tracks:
        return False, texts.tr("v.mp4_notrack")
    brand = data[top[0][1]:top[0][1] + 4].decode("latin-1", "replace")
    return True, texts.tr("v.mp4_ok", brand=brand, dur=f"{duration:.1f} s" if duration else "?", video=tracks.count("vide"), audio=tracks.count("soun"))


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
            return _pdf(data)
        if fmt == "png":
            if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
                return False, texts.tr("v.png_bad")
            w, h = struct.unpack(">II", data[16:24])
            if not (w and h):
                return False, texts.tr("v.png_zero")
            return (True, f"{w}x{h}") if data[-12:-8] == b"\x00\x00\x00\x00" and data[-8:-4] == b"IEND" else (False, texts.tr("v.png_trunc"))
        if fmt == "glb":
            return _glb(data)
        if fmt == "stl":
            head = data[:80].lstrip().lower()
            if head.startswith(b"solid") and b"endsolid" in data[-200:].lower() and b"facet" in data:
                return True, texts.tr("v.stl_ascii")
            if len(data) >= 84:
                n = struct.unpack("<I", data[80:84])[0]
                if n > 0 and len(data) == 84 + 50 * n:
                    return True, texts.tr("v.stl_bin", n=n)
            return False, texts.tr("v.stl_bad")
        if fmt in ("docx", "xlsx"):
            return _office(data, fmt)
        if fmt == "svg":
            return _svg(data)
        if fmt == "mp4":
            return _mp4(data)
    except (ValueError, UnicodeDecodeError, zipfile.BadZipFile, struct.error, csv.Error, KeyError, TypeError, AttributeError) as error:
        return False, texts.tr("v.open_fail", fmt=fmt, why=error)
    return None, texts.tr("v.no_validator_short")
