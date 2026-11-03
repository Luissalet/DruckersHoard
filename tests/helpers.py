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


def pdf():
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def zipbytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", "hello")
    return buf.getvalue()


def make_files(folder):
    files = {"source.json": b'{"scene": "demo"}', "report.pdf": pdf(), "chart.png": png(), "model.glb": glb(),
             "part.stl": stl_ascii(), "table.csv": b"a,b\n1,2\n3,4\n", "bundle.zip": zipbytes(), "notes.txt": b"free text"}
    paths = {}
    for name, data in files.items():
        (folder / name).write_bytes(data)
        paths[name] = str(folder / name)
    return paths
