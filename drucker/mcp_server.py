"""Stdio MCP bridge. Discovery (initialize, tools/list) never touches the app or the data folder; tools/call forwards
to the running app on 127.0.0.1 with the token stored in the data folder (``mcp-token``)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__
from .hoard_link import skills as family_skills
from .tools import catalogue

SKILLS = family_skills.raw("drucker", root=__file__)      # the skills this app carries, for the agent that connects


def data_folder() -> Path:
    return Path(os.environ.get("DRUCKER_DATA") or Path(__file__).resolve().parents[1] / "data")


def call_app(name, arguments):
    base = os.environ.get("DRUCKER_URL", "http://127.0.0.1:5246").rstrip("/")
    parts = urlsplit(base)
    if parts.scheme != "http" or parts.hostname not in ("127.0.0.1", "localhost") or parts.username or parts.password:
        raise RuntimeError("Drucker MCP only connects to local HTTP")
    token_file = Path(os.environ.get("DRUCKER_TOKEN_FILE") or data_folder() / "mcp-token")
    try:
        token = token_file.read_text(encoding="utf-8-sig").strip()
    except OSError:
        raise RuntimeError(f"Token file not found at {token_file}: start Drucker's Hoard once so it creates it") from None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # loopback only, never through a proxy
    try:
        with opener.open(urllib.request.Request(base + "/api/health"), timeout=5) as r:
            if json.loads(r.read()).get("service") != "drucker-hoard":
                raise RuntimeError("The configured local port is not Drucker's Hoard")
    except (urllib.error.URLError, OSError, ValueError):
        raise RuntimeError(f"Drucker's Hoard is not running at {base}. Start it with: python -m drucker") from None
    request = urllib.request.Request(base + "/api/agent/call", json.dumps({"name": name, "arguments": arguments}).encode("utf-8"),
                                     {"Content-Type": "application/json", "Authorization": "Bearer " + token}, method="POST")
    try:
        with opener.open(request, timeout=120) as r:
            return True, json.loads(r.read())["result"]
    except urllib.error.HTTPError as error:
        try:
            return False, json.loads(error.read())
        except ValueError:
            return False, {"error": f"HTTP {error.code}"}


def handle(req):
    method, params = req.get("method"), req.get("params") or {}
    own = SKILLS.answer(method, params)
    if own is not None:
        return own
    if method == "initialize":
        return SKILLS.extend(method, {"protocolVersion": params.get("protocolVersion") or "2024-11-05", "capabilities": {"tools": {}},
                                      "serverInfo": {"name": "drucker-hoard", "version": __version__}})
    if method == "ping":
        return {}
    if method == "tools/list":
        return SKILLS.extend(method, {"tools": catalogue()})
    if method == "tools/call":
        try:
            ok, body = call_app(params.get("name"), params.get("arguments") or {})
        except RuntimeError as error:
            ok, body = False, {"error": str(error)}
        return {"content": [{"type": "text", "text": json.dumps(body, ensure_ascii=False)}], "isError": not ok}
    raise LookupError(method)


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        if not line.strip():
            continue
        req = None
        try:
            req = json.loads(line)
            if "id" not in req:
                continue  # notification
            reply = {"jsonrpc": "2.0", "id": req["id"], "result": handle(req)}
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        except LookupError:
            reply = {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": "Method not found"}}
        except Exception as error:
            reply = {"jsonrpc": "2.0", "id": req.get("id") if isinstance(req, dict) else None,
                     "error": {"code": -32603, "message": f"Bridge failure: {error}"}}
        print(json.dumps(reply, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
