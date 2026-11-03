"""HTTP surface: REST for the UI, the bearer-protected agent route used by the MCP bridge, the family copilot."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, db, engagements, examples, package, proposal, review, scope, tools
from .errors import DruckerError
from .hoard_link.copilot import install_copilot
from .hoard_link.tokens import check_bearer, read_or_create_token

STATIC = Path(__file__).parent / "static"
@asynccontextmanager
async def lifespan(_app):
    token()  # create the MCP token file in the data folder at start-up
    yield


app = FastAPI(title="Drucker's Hoard", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
install_copilot(app, "drucker", str(db.data_dir()), app_name="Drucker's Hoard")


@app.middleware("http")
async def same_origin(request: Request, call_next):
    """A page on another origin must not be able to write through the browser."""
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin and urlsplit(origin).netloc != request.headers.get("host"):
        return JSONResponse({"ok": False, "error": "cross-origin request refused"}, status_code=403)
    return await call_next(request)


@app.exception_handler(DruckerError)
async def _drucker_error(request: Request, error: DruckerError):
    return JSONResponse({"ok": False, "error": str(error), **error.extra}, status_code=error.status)


def token() -> str:
    return read_or_create_token(db.data_dir() / "mcp-token")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"service": "drucker-hoard", "version": __version__}


# ---- agent route: the MCP bridge sends every tool call here with the token from the data folder
@app.get("/api/agent/tools")
def agent_tools():
    return tools.catalogue()


@app.post("/api/agent/call")
async def agent_call(request: Request, body: dict[str, Any] = Body(...)):
    if not check_bearer(request.headers.get("authorization"), token()):
        return JSONResponse({"ok": False, "error": "missing or invalid token"}, status_code=401)
    name = body.get("name") or body.get("tool")
    try:
        return {"ok": True, "tool": name, "result": tools.call(name, body.get("arguments") or {})}
    except DruckerError as error:
        return JSONResponse({"ok": False, "tool": name, "error": str(error), **error.extra}, status_code=error.status)


# ---- UI REST
@app.get("/api/example")
def example():
    return tools.call("drucker_example")


@app.post("/api/example/load")
def load_example():
    return examples.load_example()


@app.get("/api/settings")
def get_settings():
    return engagements.get_settings()


@app.put("/api/settings")
def put_settings(body: dict = Body(...)):
    return engagements.set_settings(body)


@app.get("/api/engagements")
def list_engagements(status: str | None = None, query: str | None = None):
    return engagements.list_engagements(status, query)


@app.post("/api/engagements")
def create_engagement(body: dict = Body(...)):
    body.pop("id", None)
    return engagements.save(body)


@app.get("/api/engagements/{eid}")
def get_engagement(eid: str):
    return engagements.get(eid)


@app.put("/api/engagements/{eid}")
def update_engagement(eid: str, body: dict = Body(...)):
    return engagements.save({**body, "id": eid})


@app.delete("/api/engagements/{eid}")
def delete_engagement(eid: str):
    return engagements.delete(eid)


@app.get("/api/engagements/{eid}/history")
def engagement_history(eid: str, limit: int = 200):
    return engagements.history(eid, limit)


@app.post("/api/engagements/{eid}/items/{kind}")
def add_item(eid: str, kind: str, body: dict = Body(...)):
    return engagements.save_item(eid, kind, body)


@app.put("/api/engagements/{eid}/items/{kind}/{item_id}")
def update_item(eid: str, kind: str, item_id: str, body: dict = Body(...)):
    return engagements.save_item(eid, kind, {**body, "id": item_id})


@app.delete("/api/engagements/{eid}/items/{item_id}")
def remove_item(eid: str, item_id: str):
    return engagements.delete_item(eid, item_id)


@app.post("/api/scope/compare")
def scope_compare(body: dict = Body(...)):
    return tools._scope_compare(body)


@app.post("/api/engagements/{eid}/proposal")
def make_proposal(eid: str, body: dict = Body(default={})):
    return proposal.proposal(eid, body.get("format", "json"), body.get("lang", "es"), body.get("denylist"))


@app.get("/api/engagements/{eid}/proposal.{ext}")
def download_proposal(eid: str, ext: str, lang: str = "es"):
    if ext not in ("md", "html"):
        raise DruckerError("Use .md or .html", status=404)
    out = proposal.proposal(eid, ext, lang)
    return Response(out["content"], media_type="text/markdown; charset=utf-8" if ext == "md" else "text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="propuesta.{ext}"'})


@app.post("/api/engagements/{eid}/deliverables")
def add_deliverable(eid: str, body: dict = Body(...)):
    return review.save_deliverable(eid, body.get("name"), body.get("kind", ""))


@app.get("/api/deliverables/{did}")
def get_desk(did: str):
    return review.desk(did)


@app.post("/api/deliverables/{did}/versions")
def add_version(did: str, body: dict = Body(...)):
    return review.add_version(did, body.get("file_ref"), body.get("sha256"), body.get("note", ""))


@app.post("/api/deliverables/{did}/deliver")
def select_version(did: str, body: dict = Body(...)):
    return review.set_to_deliver(did, body.get("version"))


@app.post("/api/versions/{vid}/comments")
def add_comment(vid: str, body: dict = Body(...)):
    return review.add_comment(vid, body.get("text"), body.get("author", ""), body.get("anchor"))


@app.patch("/api/comments/{cid}")
def comment_status(cid: str, body: dict = Body(...)):
    return review.set_comment_status(cid, body.get("status"), body.get("fixed_in"))


@app.post("/api/deliverables/{did}/package/verify")
def package_verify(did: str, body: dict = Body(...)):
    return package.verify_only(did, body.get("version"), body.get("spec"))


@app.post("/api/deliverables/{did}/package")
def package_build(did: str, body: dict = Body(...)):
    return package.build(did, body.get("version"), body.get("spec"))


@app.get("/api/packages/{pid}/zip")
def package_zip(pid: str):
    with db.connect() as conn:
        row = conn.execute("SELECT zip_path FROM packages WHERE id=?", (pid,)).fetchone()
    if not row or not row["zip_path"] or not Path(row["zip_path"]).is_file():
        raise DruckerError("No zip for that package (not ready, or never built)", status=404)
    return FileResponse(row["zip_path"], media_type="application/zip", filename="package.zip")
