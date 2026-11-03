import hashlib

import pytest

from drucker import engagements, review
from drucker.errors import DruckerError


@pytest.fixture
def desk(tmp_path):
    e = engagements.save({"name": "Revisión"})
    d = review.save_deliverable(e["id"], "Informe", "pdf")
    for i, body in enumerate([b"uno", b"dos", b"dos", b"cuatro"], 1):
        p = tmp_path / f"v{i}.bin"
        p.write_bytes(body)
        d = review.add_version(d["id"], str(p))
    return d


def test_versions_are_numbered_and_hashed(desk):
    assert [v["n"] for v in desk["versions"]] == [1, 2, 3, 4]
    assert desk["versions"][0]["sha256"] == hashlib.sha256(b"uno").hexdigest() and desk["versions"][0]["hash_source"] == "computed"


def test_declared_hash_must_match_file(tmp_path):
    e = engagements.save({"name": "x"})
    d = review.save_deliverable(e["id"], "A")
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc")
    with pytest.raises(DruckerError):
        review.add_version(d["id"], str(p), sha256="0" * 64)
    unknown = review.add_version(d["id"], "https://ejemplo.invalid/f", sha256="a" * 64)
    assert unknown["versions"][0]["hash_source"] == "declared"


def test_feedback_on_an_older_version_is_recognised_as_stale(desk):
    d = review.add_comment(desk["versions"][0]["id"], "El título está mal", "Cliente", {"kind": "page", "value": 1})
    c = d["comments"][0]
    assert c["stale"] is True and c["later_versions"] == [2, 3, 4] and c["addressed_by"] is None
    assert "v2 to v4" in c["note"]
    d = review.add_comment(d["versions"][3]["id"], "Falta el logo")
    latest = next(c for c in d["comments"] if c["version"] == 4)
    assert latest["stale"] is False
    assert d["counts"]["stale"] == 1 and d["counts"]["open"] == 2


def test_identical_content_in_a_later_version_keeps_feedback_current(desk):
    d = review.add_comment(desk["versions"][1]["id"], "Revisar el segundo párrafo")   # v2 and v3 have the same hash
    assert d["comments"][0]["later_versions"] == [4]            # v3 is identical, only v4 differs
    e = engagements.save({"name": "y"})
    d2 = review.save_deliverable(e["id"], "Otro")
    p = review.add_version(d2["id"], "https://ejemplo.invalid/a", sha256="b" * 64)
    p = review.add_version(p["id"], "https://ejemplo.invalid/b", sha256="b" * 64)
    p = review.add_comment(p["versions"][0]["id"], "Igual")
    assert p["comments"][0]["stale"] is False and "identical" in p["comments"][0]["note"]


def test_fixed_requires_a_later_version_and_reports_which(desk):
    d = review.add_comment(desk["versions"][1]["id"], "Corregir cifra")
    cid = d["comments"][0]["id"]
    with pytest.raises(DruckerError):
        review.set_comment_status(cid, "fixed")
    with pytest.raises(DruckerError):
        review.set_comment_status(cid, "fixed", fixed_in=2)
    d = review.set_comment_status(cid, "fixed", fixed_in=4)
    c = d["comments"][0]
    assert c["status"] == "fixed" and c["addressed_by"] == 4 and c["stale"] is False
    d = review.set_comment_status(cid, "wontfix")
    assert d["comments"][0]["fixed_in"] is None and d["counts"]["wontfix"] == 1
    d = review.set_comment_status(cid, "open")
    assert d["comments"][0]["status"] == "open"


def test_anchors_are_validated(desk):
    vid = desk["versions"][0]["id"]
    d = desk
    for anchor in ({"kind": "page", "value": 3}, {"kind": "region", "value": [1, 2, 3, 4]}, {"kind": "time", "value": {"start": 2.5, "end": 4}},
                   {"kind": "object", "value": "B7"}):
        d = review.add_comment(vid, "c", anchor=anchor)
    assert [c["anchor"]["kind"] for c in d["comments"]] == ["page", "region", "time", "object"]
    for bad in ({"kind": "line", "value": 1}, {"kind": "time", "value": {"start": 9, "end": 1}}, {"kind": "page"}):
        with pytest.raises(DruckerError):
            review.add_comment(vid, "c", anchor=bad)


def test_exactly_one_version_to_deliver_and_warnings(desk):
    d = desk
    assert d["to_deliver"] is None and "No version selected to deliver." in d["warnings"] and d["ready_to_deliver"] is False
    d = review.set_to_deliver(d["id"], 2)
    assert d["to_deliver"] == 2 and any("not the latest" in w for w in d["warnings"])
    d = review.set_to_deliver(d["id"], 4)
    assert d["to_deliver"] == 4 and d["ready_to_deliver"] is True and d["warnings"] == []
    d = review.add_comment(d["versions"][3]["id"], "Bloquea")
    assert d["ready_to_deliver"] is False and any("open comment" in w for w in d["warnings"])
    assert sum(1 for v in d["versions"] if v["n"] == d["to_deliver"]) == 1
    with pytest.raises(DruckerError):
        review.set_to_deliver(d["id"], 9)


def test_review_events_land_in_the_engagement_history(desk):
    review.add_comment(desk["versions"][0]["id"], "x")
    summaries = [h["summary"] for h in engagements.history(desk["engagement_id"])]
    assert any("version 4 added" in s for s in summaries) and any("comment added" in s for s in summaries)
