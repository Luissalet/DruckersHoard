import json
import os
import socket
import subprocess
import sys
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

from drucker import tools
from drucker.app import app
from helpers import make_files

EXPECTED = {"drucker_engagements", "drucker_engagement_get", "drucker_engagement_save", "drucker_item_save", "drucker_item_delete",
            "drucker_history", "drucker_scope_compare", "drucker_proposal", "drucker_review", "drucker_deliverable_save",
            "drucker_version_add", "drucker_comment_add", "drucker_comment_status", "drucker_deliver_select", "drucker_package_verify",
            "drucker_package", "drucker_settings", "drucker_example", "drucker_bands_suggest", "drucker_refs_resolve", "drucker_synonyms",
            "drucker_proposal_templates", "drucker_scope_decide", "drucker_change_orders"}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_and_token_file_created_at_start(client, data_dir):
    assert client.get("/api/health").json()["service"] == "drucker-hoard"
    assert len((data_dir / "mcp-token").read_text().strip()) >= 32


def test_ui_and_static_are_served(client):
    html = client.get("/").text
    assert 'data-hoard-app="drucker"' in html and "Oficina de encargos" in html or "Drucker" in html
    assert client.get("/static/app.js").status_code == 200 and client.get("/static/hoard-theme.css").status_code == 200
    assert client.get("/api/copilot/launcher.js").status_code == 200
    assert client.get("/api/copilot/info").status_code in (200, 503)       # 503 only because no Faustus is configured here


def test_full_rest_flow(client, tmp_path):
    files = make_files(tmp_path)
    e = client.post("/api/engagements", json={"name": "REST", "client_name": "Ficticio", "budget_min": 1, "budget_max": 2}).json()
    eid = e["id"]
    client.put(f"/api/engagements/{eid}", json={"status": "active"})
    s = client.post(f"/api/engagements/{eid}/items/scope", json={"title": "Informe", "status": "agreed"}).json()
    assert client.put(f"/api/engagements/{eid}/items/scope/{s['id']}", json={"status": "done"}).json()["status"] == "done"
    assert client.post(f"/api/engagements/{eid}/items/milestone", json={"title": "H", "due": "no"}).status_code == 422
    d = client.post(f"/api/engagements/{eid}/deliverables", json={"name": "Informe", "kind": "pdf"}).json()
    desk = client.post(f"/api/deliverables/{d['id']}/versions", json={"file_ref": files["report.pdf"]}).json()
    desk = client.post(f"/api/deliverables/{d['id']}/versions", json={"file_ref": files["chart.png"]}).json()
    c = client.post(f"/api/versions/{desk['versions'][0]['id']}/comments", json={"text": "Mal", "anchor": {"kind": "page", "value": 1}}).json()
    assert c["comments"][0]["stale"] is True
    fixed = client.patch(f"/api/comments/{c['comments'][0]['id']}", json={"status": "fixed", "fixed_in": 2}).json()
    assert fixed["comments"][0]["addressed_by"] == 2
    assert client.post(f"/api/deliverables/{d['id']}/deliver", json={"version": 2}).json()["ready_to_deliver"] is True
    spec = {"editable_files": [files["chart.png"]], "instructions": "Abrir", "limitations": ["Ejemplo"]}
    assert client.post(f"/api/deliverables/{d['id']}/package/verify", json={"version": 2, "spec": spec}).json()["ready"] is True
    built = client.post(f"/api/deliverables/{d['id']}/package", json={"version": 2, "spec": spec}).json()
    assert built["ready"] and client.get(f"/api/packages/{built['id']}/zip").headers["content-type"] == "application/zip"
    bad = client.post(f"/api/deliverables/{d['id']}/package", json={"version": 2, "spec": {**spec, "limitations": []}}).json()
    assert bad["ready"] is False and client.get(f"/api/packages/{bad['id']}/zip").status_code == 404
    hist = client.get(f"/api/engagements/{eid}/history").json()
    assert len(hist) >= 8 and hist[-1]["action"] == "create"
    assert client.get("/api/engagements/nope").status_code == 404
    client.delete(f"/api/engagements/{eid}")
    assert client.get(f"/api/engagements/{eid}").status_code == 404


def test_scope_and_proposal_endpoints(client):
    ex = client.get("/api/example").json()
    r = client.post("/api/scope/compare", json=ex["scope_compare"]).json()
    assert r["counts"]["added"] == 2 and r["counts"]["ambiguous"] == 2
    assert client.post("/api/scope/compare", json={"request": ""}).status_code == 422
    e = client.post("/api/example/load").json()
    assert client.post(f"/api/engagements/{e['id']}/proposal", json={"format": "md"}).json()["content"].startswith("# Propuesta")
    assert client.get(f"/api/engagements/{e['id']}/proposal.html").headers["content-disposition"].endswith('propuesta.html"')
    client.post(f"/api/engagements/{e['id']}/items/scope", json={"title": "Integrar con Faustus", "status": "agreed"})
    refused = client.get(f"/api/engagements/{e['id']}/proposal.md")
    assert refused.status_code == 422 and refused.json()["violations"][0]["term"] == "Faustus"


def test_cross_origin_writes_are_refused(client):
    r = client.post("/api/engagements", json={"name": "x"}, headers={"Origin": "https://otro.example"})
    assert r.status_code == 403


def test_agent_route_requires_the_token_and_lists_tools(client, data_dir):
    assert client.post("/api/agent/call", json={"name": "drucker_engagements"}).status_code == 401
    assert client.post("/api/agent/call", json={"name": "drucker_engagements"}, headers={"Authorization": "Bearer nope"}).status_code == 401
    token = (data_dir / "mcp-token").read_text().strip()
    ok = client.post("/api/agent/call", json={"name": "drucker_engagements"}, headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200 and ok.json() == {"ok": True, "tool": "drucker_engagements", "result": []}
    bad = client.post("/api/agent/call", json={"name": "drucker_engagement_get", "arguments": {}}, headers={"Authorization": f"Bearer {token}"})
    assert bad.status_code == 422 and "engagement_id" in bad.json()["error"]
    assert client.post("/api/agent/call", json={"name": "nope"}, headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert {t["name"] for t in client.get("/api/agent/tools").json()} == EXPECTED


def test_catalogue_conventions():
    cat = tools.catalogue()
    assert {t["name"] for t in cat} == EXPECTED and all(t["name"].startswith("drucker_") for t in cat)
    by = {t["name"]: t for t in cat}
    for name in ("drucker_engagements", "drucker_engagement_get", "drucker_history", "drucker_scope_compare", "drucker_review",
                 "drucker_package_verify", "drucker_example", "drucker_bands_suggest", "drucker_refs_resolve", "drucker_proposal_templates",
                 "drucker_change_orders"):
        assert by[name]["annotations"]["readOnlyHint"] is True, name
    for name in ("drucker_engagement_save", "drucker_item_save", "drucker_package", "drucker_comment_add", "drucker_version_add", "drucker_proposal", "drucker_scope_decide"):
        assert by[name]["annotations"]["readOnlyHint"] is False, name
    assert by["drucker_item_delete"]["annotations"]["destructiveHint"] is True
    assert all(t["annotations"]["openWorldHint"] is False and t["inputSchema"]["additionalProperties"] is False for t in cat)
    with pytest.raises(Exception):
        tools.call("drucker_item_save", {"engagement_id": "x", "kind": "scope", "item": {}, "extra": 1})


# ---- the real stdio bridge, against a real HTTP server
def rpc(proc, method, params=None, id_=1):
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def bridge(env):
    return subprocess.Popen([sys.executable, "-m", "drucker.mcp_server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
                            env={**os.environ, **env}, cwd=os.path.dirname(os.path.dirname(__file__)))


def test_mcp_discovery_starts_no_http_and_touches_no_data(tmp_path):
    folder = tmp_path / "untouched"
    p = bridge({"DRUCKER_DATA": str(folder), "DRUCKER_URL": "http://127.0.0.1:1"})
    try:
        init = rpc(p, "initialize", {"protocolVersion": "2024-11-05"})
        assert init["result"]["serverInfo"]["name"] == "drucker-hoard"
        listed = rpc(p, "tools/list", id_=2)["result"]["tools"]
        assert {t["name"] for t in listed} == EXPECTED
        down = rpc(p, "tools/call", {"name": "drucker_engagements", "arguments": {}}, id_=3)["result"]
        assert down["isError"] is True and "Token file not found" in down["content"][0]["text"]
        assert "error" in rpc(p, "nope", id_=4)
    finally:
        p.terminate()
        p.wait(5)
    assert not folder.exists()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_mcp_calls_reach_the_running_app_with_the_token_file(data_dir, tmp_path):
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    p = bridge({"DRUCKER_DATA": str(data_dir), "DRUCKER_URL": f"http://127.0.0.1:{port}"})
    try:
        rpc(p, "initialize")

        def call(name, args, id_):
            r = rpc(p, "tools/call", {"name": name, "arguments": args}, id_=id_)["result"]
            return r["isError"], json.loads(r["content"][0]["text"])

        err, e = call("drucker_engagement_save", {"name": "Vía MCP", "client_name": "Ficticio", "items": {"scope": [{"title": "Informe", "status": "agreed"}]}}, 2)
        assert not err and e["items"]["scope"][0]["title"] == "Informe"
        err, listed = call("drucker_engagements", {}, 3)
        assert not err and [x["name"] for x in listed] == ["Vía MCP"]
        err, cmp_ = call("drucker_scope_compare", {"engagement_id": e["id"], "request": "Informe en DOCX\nUna app móvil"}, 4)
        assert not err and cmp_["counts"]["added"] + cmp_["counts"]["ambiguous"] == 2
        err, d = call("drucker_deliverable_save", {"engagement_id": e["id"], "name": "Informe"}, 5)
        f = make_files(tmp_path)
        err, d = call("drucker_version_add", {"deliverable_id": d["id"], "file_ref": f["report.pdf"]}, 6)
        err, pk = call("drucker_package", {"deliverable_id": d["id"], "version": 1, "spec": {"instructions": "x y", "limitations": ["l"]}}, 7)
        assert not err and pk["ready"] is True and pk["zip_path"]
        err, bad = call("drucker_engagement_get", {"engagement_id": "nope"}, 8)
        assert err and "not found" in bad["error"]
        err, ref = call("drucker_proposal", {"engagement_id": e["id"], "format": "md", "lang": "en"}, 9)
        assert err and "MCP" in ref["error"] and ref["violations"][0]["sentence_id"] == "title"   # the engagement name holds an internal term
        err, ref = call("drucker_proposal", {"engagement_id": e["id"], "format": "md", "lang": "en", "denylist": []}, 10)
        assert not err and ref["content"].startswith("# Proposal")
    finally:
        p.terminate()
        p.wait(5)
        server.should_exit = True
        thread.join(5)
