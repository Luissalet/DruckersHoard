"""DOCX, XLSX, SVG and MP4 validation, deeper PDF and GLB checks, and the Vulcan glTF validator through the family bus."""
import io
import zipfile

import pytest

from drucker import engagements, formats, links, package, review
from helpers import docx, glb, glb_full, glb_with, mp4, pdf, svg, xlsx


def check(tmp_path, name, data, fmt=None):
    p = tmp_path / name
    p.write_bytes(data)
    return formats.validate_format(p, fmt)


@pytest.mark.parametrize("name,data", [("a.docx", docx()), ("a.xlsx", xlsx()), ("a.svg", svg()), ("a.mp4", mp4()), ("a.m4v", mp4()),
                                       ("a.pdf", pdf(2)), ("a.glb", glb_full())])
def test_good_files_pass(tmp_path, name, data):
    ok, detail = check(tmp_path, name, data)
    assert ok is True, detail


def _without(data, part):
    src = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in src.namelist():
            if n != part:
                z.writestr(n, src.read(n))
    return buf.getvalue()


def test_docx_must_be_a_package_with_a_document_part(tmp_path):
    assert check(tmp_path, "x.docx", b"not a zip")[0] is False
    assert check(tmp_path, "y.docx", _without(docx(), "word/document.xml"))[0] is False
    assert check(tmp_path, "z.docx", _without(docx(), "[Content_Types].xml"))[0] is False


def test_xlsx_must_have_sheets_and_the_parts_they_point_to(tmp_path):
    assert check(tmp_path, "x.xlsx", _without(xlsx(), "xl/workbook.xml"))[0] is False
    assert check(tmp_path, "y.xlsx", _without(xlsx(), "xl/worksheets/sheet2.xml"))[0] is False
    assert check(tmp_path, "z.xlsx", xlsx(sheets=()))[0] is False


@pytest.mark.parametrize("data", [b"<svg", b"<html></html>", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 0 0"><rect/></svg>',
                                  b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'])
def test_broken_or_empty_svg_fails(tmp_path, data):
    assert check(tmp_path, "x.svg", data)[0] is False


def test_mp4_needs_moov_and_media(tmp_path):
    assert check(tmp_path, "a.mp4", mp4(with_moov=False))[0] is False
    assert check(tmp_path, "b.mp4", mp4(with_mdat=False))[0] is False
    assert check(tmp_path, "c.mp4", mp4(tracks=()))[0] is False
    assert check(tmp_path, "e.mp4", b"\0\0\0\x08free")[0] is False
    ok, detail = check(tmp_path, "f.mp4", mp4(tracks=(b"vide", b"soun")))
    assert ok is True and detail


def test_pdf_checks_structure_not_just_the_header(tmp_path):
    good = pdf(3)
    assert check(tmp_path, "a.pdf", good)[0] is True
    assert check(tmp_path, "b.pdf", good.replace(b"startxref", b"startxxxx"))[0] is False
    assert check(tmp_path, "c.pdf", good[:60] + b"%%EOF")[0] is False
    assert check(tmp_path, "d.pdf", b"%PDF-1.4\n%%EOF")[0] is False


def test_glb_checks_chunks_accessors_and_buffer_ranges(tmp_path):
    ok, _ = check(tmp_path, "a.glb", glb_full())
    assert ok is True
    assert check(tmp_path, "b.glb", glb_full()[:-6])[0] is False
    assert check(tmp_path, "c.glb", glb_with({"asset": {"version": "2.0"}, "buffers": [{"byteLength": 9999}]}, b"\0" * 12))[0] is False
    assert check(tmp_path, "d.glb", glb_with({"asset": {"version": "1.0"}}))[0] is False
    assert check(tmp_path, "e.glb", glb_with({"asset": {"version": "2.0"}, "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 100}], "buffers": [{"byteLength": 12}]}, b"\0" * 12))[0] is False


# ---- the Khronos validator in Vulcan, through the hub
def _vulcan(monkeypatch, answer):
    seen = []

    def fake(owner, tool, args=None, timeout=10):
        seen.append((owner, tool, args))
        return answer

    monkeypatch.setattr(links, "call", fake)
    return seen


def _glb_package(tmp_path):
    f = tmp_path / "m.glb"
    f.write_bytes(glb_full())
    (tmp_path / "s.json").write_text("{}")
    e = engagements.save({"name": "GLB"})
    d = review.add_version(review.save_deliverable(e["id"], "Modelo", "glb")["id"], str(tmp_path / "s.json"))
    spec = {"editable_files": [str(tmp_path / "s.json")], "exports": [str(f)], "data_sources": [], "instructions": "Abrir.", "limitations": ["Ejemplo"]}
    return d, spec


def test_vulcan_errors_make_the_glb_fail(monkeypatch, tmp_path):
    d, spec = _glb_package(tmp_path)
    seen = _vulcan(monkeypatch, {"ok": True, "data": {"status": "done", "errors": 2, "warnings": 1, "summary": {"label": "2 errors"}}})
    r = package.verify_only(d["id"], 1, spec)
    assert r["ready"] is False and any("glb_khronos" in c["id"] for c in r["failed"])
    assert seen[0][:2] == ("vulcan", "gltf_validate") and seen[0][2]["path"].endswith("m.glb")


def test_vulcan_clean_and_vulcan_absent(monkeypatch, tmp_path):
    d, spec = _glb_package(tmp_path)
    _vulcan(monkeypatch, {"ok": True, "data": {"status": "done", "errors": 0, "warnings": 3, "summary": {}}})
    assert package.verify_only(d["id"], 1, spec)["ready"] is True
    # Vulcan not running: the local structural checks still decide, nothing is blocked by a missing neighbour
    _vulcan(monkeypatch, {"ok": False, "kind": "app_down", "error": "down", "data": None, "status": None})
    r = package.verify_only(d["id"], 1, spec)
    assert r["ready"] is True


def test_new_formats_go_through_the_package(tmp_path):
    (tmp_path / "s.json").write_text("{}")
    paths = {n: str(tmp_path / n) for n in ("a.docx", "a.xlsx", "a.svg", "a.mp4")}
    for n, data in (("a.docx", docx()), ("a.xlsx", xlsx()), ("a.svg", svg()), ("a.mp4", mp4())):
        (tmp_path / n).write_bytes(data)
    e = engagements.save({"name": "Formatos"})
    d = review.add_version(review.save_deliverable(e["id"], "Todo", "zip")["id"], str(tmp_path / "s.json"))
    spec = {"editable_files": [str(tmp_path / "s.json")], "exports": list(paths.values()), "data_sources": [], "instructions": "Abrir.", "limitations": ["x"]}
    assert package.verify_only(d["id"], 1, spec)["ready"] is True
    (tmp_path / "a.docx").write_bytes(b"PK broken")
    r = package.verify_only(d["id"], 1, spec)
    assert r["ready"] is False and any("a.docx" in c["id"] for c in r["failed"])
