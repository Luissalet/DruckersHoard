"""SQLite storage in the data directory (``DRUCKER_DATA``, default ``<repo>/data``)."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import texts

SCHEMA = """
CREATE TABLE IF NOT EXISTS engagements (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, client_name TEXT NOT NULL DEFAULT '', client_ref TEXT,
  origin TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'lead', currency TEXT NOT NULL DEFAULT 'EUR',
  budget_min REAL, budget_max REAL, notes TEXT NOT NULL DEFAULT '', denylist TEXT,
  created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY, engagement_id TEXT NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
  kind TEXT NOT NULL, body TEXT NOT NULL, seq INTEGER NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS items_by_eng ON items(engagement_id, kind, seq);
CREATE TABLE IF NOT EXISTS history (
  id INTEGER PRIMARY KEY AUTOINCREMENT, engagement_id TEXT NOT NULL, ts TEXT NOT NULL, action TEXT NOT NULL,
  entity TEXT NOT NULL, entity_id TEXT, summary TEXT NOT NULL, changes TEXT, msg TEXT);
CREATE INDEX IF NOT EXISTS history_by_eng ON history(engagement_id, id);
CREATE TABLE IF NOT EXISTS deliverables (
  id TEXT PRIMARY KEY, engagement_id TEXT NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
  name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT '', to_deliver_version_id TEXT, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS versions (
  id TEXT PRIMARY KEY, deliverable_id TEXT NOT NULL REFERENCES deliverables(id) ON DELETE CASCADE,
  n INTEGER NOT NULL, file_ref TEXT NOT NULL, sha256 TEXT, hash_source TEXT NOT NULL DEFAULT 'none',
  note TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, UNIQUE(deliverable_id, n));
CREATE TABLE IF NOT EXISTS comments (
  id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES versions(id) ON DELETE CASCADE,
  text TEXT NOT NULL, author TEXT NOT NULL DEFAULT '', anchor TEXT, status TEXT NOT NULL DEFAULT 'open',
  fixed_in_version_id TEXT, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS packages (
  id TEXT PRIMARY KEY, version_id TEXT NOT NULL, ready INTEGER NOT NULL, manifest TEXT NOT NULL,
  zip_path TEXT, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def data_dir() -> Path:
    root = Path(os.environ.get("DRUCKER_DATA") or Path(__file__).resolve().parents[1] / "data")
    root.mkdir(parents=True, exist_ok=True)
    return root


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@contextmanager
def connect():
    db = sqlite3.connect(data_dir() / "drucker.db", timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(SCHEMA)
        for alter in ("ALTER TABLE history ADD COLUMN msg TEXT",  # databases created before history messages were translatable
                      "ALTER TABLE engagements ADD COLUMN kind TEXT NOT NULL DEFAULT 'general'"):  # ... and before the engagement type
            try:
                db.execute(alter)
            except sqlite3.OperationalError:
                pass
        with db:
            yield db
    finally:
        db.close()


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def loads(text, default=None):
    return json.loads(text) if text else default


def render_msg(key, params, lang=None):
    """A history message in the asked language; item kinds and comment statuses are translated too."""
    params = dict(params or {})
    if "kind" in params:
        params["kind"] = texts.tr("kind." + params["kind"], lang)
    if "status" in params:
        params["status"] = texts.tr("status." + params["status"], lang)
    return texts.tr(key, lang, **params)


def log(db, engagement_id, action, entity, entity_id, key, params=None, changes=None):
    """Write one history line. ``key`` + ``params`` are kept so the timeline can be shown in either language."""
    db.execute("INSERT INTO history(engagement_id,ts,action,entity,entity_id,summary,changes,msg) VALUES(?,?,?,?,?,?,?,?)",
               (engagement_id, now(), action, entity, entity_id, render_msg(key, params, "en"), dumps(changes) if changes else None,
                dumps({"key": key, "params": params or {}})))
