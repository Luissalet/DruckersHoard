import json
import zipfile
from pathlib import Path

import pytest

from drucker import db, engagements, package, review
from drucker.errors import DruckerError
from helpers import glb, make_files, png, stl_binary


@pytest.fixture
def setup(tmp_path):
    files = make_files(tmp_path)
    e = engagements.save({"name": "Paquete"})
    d = review.save_deliverable(e["id"], "Modelo 3D", "glb")
    d = review.add_version(d["id"], files["source.json"])
    spec = {"editable_files": [files["source.json"]], "exports": [files["model.glb"], files["report.pdf"], files["chart.png"], files["part.stl"], files["table.csv"], files["bundle.zip"]],
            "data_sources": [{"name": "ventas.csv", "authorised": True}], "instructions": "Abrir source.json y volver a exportar.",
            "examples": [files["notes.txt"]], "limitations": ["Solo probado con datos de ejemplo"]}
    return d, files, spec, tmp_path


def failed(r):
    return {c["id"] for c in r["checks"] if not c["ok"]}


def test_complete_package_passes_and_writes_manifest_and_zip(setup):
    d, files, spec, _ = setup
    r = package.build(d["id"], 1, spec)
    assert r["ready"] is True and r["failed"] == [] and r["zip_path"]
    with zipfile.ZipFile(r["zip_path"]) as z:
        names = set(z.namelist())
        assert {"manifest.json", "INSTRUCTIONS.md", "LIMITATIONS.md", "data-sources.json", "editables/source.json", "exports/model.glb", "examples/notes.txt"} <= names
        manifest = json.loads(z.read("manifest.json"))
    assert manifest["ready"] is True and manifest["version"] == 1 and len(manifest["files"]) == 8
    assert (Path(r["zip_path"]).parent / "manifest.json").is_file()
    assert any(c["id"] == "zip_roundtrip" and c["ok"] for c in r["checks"])


def test_missing_file_makes_it_not_ready_and_writes_no_zip(setup):
    d, files, spec, tmp = setup
    spec["exports"].append(str(tmp / "no-existe.pdf"))
    r = package.build(d["id"], 1, spec)
    assert r["ready"] is False and r["zip_path"] is None
    assert any(c["id"].startswith("file:export:") and "no-existe" in c["id"] for c in r["failed"])
    assert not list((db.data_dir() / "packages").rglob("package.zip"))


def test_hash_mismatch_fails(setup):
    d, files, spec, _ = setup
    spec["exports"][0] = {"path": files["model.glb"], "sha256": "0" * 64}
    assert any(i.startswith("hash:export:") for i in failed(package.build(d["id"], 1, spec)))


def test_version_file_changed_after_recording_fails(setup):
    d, files, spec, tmp = setup
    (tmp / "source.json").write_text('{"changed": true}')
    assert "version_hash" in failed(package.verify_only(d["id"], 1, spec))


@pytest.mark.parametrize("name,data", [("bad.png", png()[:-8]), ("bad.pdf", b"%PDF-1.4 no end"), ("bad.glb", glb()[:-4]),
                                       ("bad.stl", b"solid x\nnothing"), ("bad.json", b"{oops"), ("bad.csv", b"a,b\n1\n"),
                                       ("bad.zip", b"PK not a zip")])
def test_broken_exports_do_not_open(setup, name, data):
    d, files, spec, tmp = setup
    (tmp / name).write_bytes(data)
    spec["exports"] = [str(tmp / name)]
    r = package.verify_only(d["id"], 1, spec)
    assert r["ready"] is False and any(i.startswith("format:export:") for i in failed(r))


def test_binary_stl_and_empty_file(setup):
    d, files, spec, tmp = setup
    (tmp / "b.stl").write_bytes(stl_binary())
    (tmp / "empty.json").write_bytes(b"")
    assert package.verify_only(d["id"], 1, {**spec, "exports": [str(tmp / "b.stl")]})["ready"] is True
    assert package.verify_only(d["id"], 1, {**spec, "exports": [str(tmp / "empty.json")]})["ready"] is False


def test_unauthorised_source_missing_instructions_and_limitations_fail(setup):
    d, files, spec, _ = setup
    bad = {**spec, "data_sources": [{"name": "clientes.csv", "authorised": False}], "instructions": "  ", "limitations": []}
    assert {"source:clientes.csv", "instructions", "limitations"} <= failed(package.verify_only(d["id"], 1, bad))


def test_remote_references_cannot_be_verified_so_they_fail(setup):
    d, files, spec, _ = setup
    spec["exports"] = ["https://ejemplo.invalid/informe.pdf"]
    assert package.verify_only(d["id"], 1, spec)["ready"] is False


def test_default_editable_file_is_the_versions_own_file(setup):
    d, files, spec, _ = setup
    r = package.verify_only(d["id"], 1, {k: v for k, v in spec.items() if k != "editable_files"})
    assert r["ready"] is True


def test_verify_only_leaves_no_trace_but_build_is_recorded(setup):
    d, files, spec, _ = setup
    before = len(engagements.history(d["engagement_id"]))
    package.verify_only(d["id"], 1, spec)
    assert len(engagements.history(d["engagement_id"])) == before and not (db.data_dir() / "packages").exists()
    package.build(d["id"], 1, spec)
    assert "package ready" in engagements.history(d["engagement_id"])[0]["summary"]


def test_same_inputs_give_identical_zip_bytes(setup):
    d, files, spec, _ = setup
    a = package.build(d["id"], 1, spec)["zip_path"]
    first = open(a, "rb").read()
    b = package.build(d["id"], 1, spec)["zip_path"]
    assert first == open(b, "rb").read()


def test_unknown_deliverable():
    with pytest.raises(DruckerError):
        package.build("nope", 1, {})
