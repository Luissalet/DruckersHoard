"""Fixtures built in code: tiny valid files in several formats."""
import io
import json
import struct
import zipfile
import zlib


def png(w=2, h=2):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def glb():
    body = json.dumps({"asset": {"version": "2.0"}}).encode()
    body += b" " * (-len(body) % 4)
    return b"glTF" + struct.pack("<II", 2, 12 + 8 + len(body)) + struct.pack("<II", len(body), 0x4E4F534A) + body


def stl_ascii():
    return b"solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n"


def stl_binary():
    return b"\0" * 80 + struct.pack("<I", 1) + b"\0" * 50


def pdf(pages=1):
    """A small but complete PDF: catalog, page tree, pages, a real cross-reference table and trailer."""
    kids = " ".join(f"{3 + i} 0 R" for i in range(pages))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode()]
    objs += [b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>" for _ in range(pages)]
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n" + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    return out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def glb_full():
    """A GLB with a binary chunk: one triangle (3 float vec3 positions) wired through buffer, view, accessor, mesh, node and scene."""
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36}], "buffers": [{"byteLength": 36}]}
    body = json.dumps(doc).encode()
    body += b" " * (-len(body) % 4)
    binary = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    total = 12 + 8 + len(body) + 8 + len(binary)
    return (b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(body), 0x4E4F534A) + body
            + struct.pack("<II", len(binary), 0x004E4942) + binary)


def glb_with(doc, binary=b""):
    body = json.dumps(doc).encode()
    body += b" " * (-len(body) % 4)
    binary += b"\0" * (-len(binary) % 4)
    total = 12 + 8 + len(body) + ((8 + len(binary)) if binary else 0)
    out = b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(body), 0x4E4F534A) + body
    return out + (struct.pack("<II", len(binary), 0x004E4942) + binary if binary else b"")


def _zip(parts):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)
    return buf.getvalue()


_CT = '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>'
_RELS = '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def docx(text="Hola mundo de prueba"):
    return _zip({"[Content_Types].xml": _CT, "_rels/.rels": _RELS,
                 "word/document.xml": f'<?xml version="1.0"?><w:document xmlns:w="{_W}"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>'})


def xlsx(sheets=("Ventas", "Resumen")):
    wb = f'<?xml version="1.0"?><workbook xmlns="{_S}" xmlns:r="{_R}"><sheets>' + "".join(
        f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(sheets, 1)) + "</sheets></workbook>"
    rels = '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(
        f'<Relationship Id="rId{i}" Type="x" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1)) + "</Relationships>"
    parts = {"[Content_Types].xml": _CT, "_rels/.rels": _RELS, "xl/workbook.xml": wb, "xl/_rels/workbook.xml.rels": rels}
    for i in range(1, len(sheets) + 1):
        parts[f"xl/worksheets/sheet{i}.xml"] = f'<?xml version="1.0"?><worksheet xmlns="{_S}"><sheetData/></worksheet>'
    return _zip(parts)


def svg(viewbox="0 0 100 50"):
    return f'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}"><rect width="10" height="10"/><circle r="4"/></svg>'.encode()


def _box(kind, payload=b""):
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def mp4(tracks=(b"vide",), duration_s=3, with_moov=True, with_mdat=True):
    mvhd = _box(b"mvhd", struct.pack(">B3xIIII", 0, 0, 0, 1000, duration_s * 1000) + b"\0" * 80)
    traks = b"".join(_box(b"trak", _box(b"mdia", _box(b"hdlr", struct.pack(">B3xI4s", 0, 0, t) + b"\0" * 12))) for t in tracks)
    out = _box(b"ftyp", b"isom" + struct.pack(">I", 512) + b"isom")
    if with_moov:
        out += _box(b"moov", mvhd + traks)
    if with_mdat:
        out += _box(b"mdat", b"\0" * 16)
    return out


def zipbytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", "hello")
    return buf.getvalue()


def make_files(folder):
    files = {"source.json": b'{"scene": "demo"}', "report.pdf": pdf(), "chart.png": png(), "model.glb": glb_full(),
             "part.stl": stl_ascii(), "table.csv": b"a,b\n1,2\n3,4\n", "bundle.zip": zipbytes(), "notes.txt": b"free text",
             "doc.docx": docx(), "book.xlsx": xlsx(), "logo.svg": svg(), "clip.mp4": mp4()}
    paths = {}
    for name, data in files.items():
        (folder / name).write_bytes(data)
        paths[name] = str(folder / name)
    return paths
