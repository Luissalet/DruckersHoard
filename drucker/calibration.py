"""Effort bands proposed from the real hours recorded in closed engagements, with how scattered those hours are.

Every ``effort`` item (family, part, hours, units) is one sample: hours per unit. A band part with three or more samples is
proposed as the 10th-90th percentile range; with fewer it is the observed minimum-maximum and is marked insufficient. The
proposal never changes anything by itself: apply it with ``drucker_settings {bands}`` or the button in Compare scope."""
from __future__ import annotations

import math
import statistics

from . import db, engagements, scope, texts
from .errors import err

MIN_SAMPLES = 3
WIDE_CV = 0.6      # stdev / mean above this: the hours are too scattered to trust one range


def quantile(values, q):
    """Linear-interpolated quantile of a non-empty list."""
    v = sorted(values)
    if len(v) == 1:
        return v[0]
    pos = (len(v) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def _round(x):
    return round(x + 1e-9, 1)


def _samples(status):
    with db.connect() as conn:
        rows = conn.execute("SELECT i.id, i.body, e.id AS eid, e.name, e.status FROM items i JOIN engagements e ON e.id=i.engagement_id "
                            "WHERE i.kind='effort' ORDER BY e.created, i.seq").fetchall()
    out = []
    for r in rows:
        if status != "any" and r["status"] != status:
            continue
        b = db.loads(r["body"])
        hours, units = float(b.get("hours") or 0), float(b.get("units") or 1)
        if hours <= 0 or units <= 0 or b.get("family") not in scope.DEFAULT_BANDS:
            continue
        out.append({"engagement_id": r["eid"], "engagement": r["name"], "item_id": r["id"], "title": b.get("title", ""), "family": b["family"],
                    "part": b.get("part"), "hours": hours, "units": units, "per_unit": hours / units})
    return out


@texts.localized
def suggest(status="closed", min_samples=MIN_SAMPLES):
    """Proposed bands per family/part with n, min, max, mean, median, stdev, p10, p90 and a reliability word:
    ``insufficient`` (under ``min_samples``), ``scattered`` (stdev above 60 % of the mean) or ``ok``. ``bands`` holds only the
    parts that reach ``min_samples`` and is ready to send to ``drucker_settings``."""
    if status not in ("closed", "active", "paused", "lead", "any"):
        raise err("e.status_filter")
    if isinstance(min_samples, bool) or not isinstance(min_samples, int) or not 1 <= min_samples <= 1000:
        raise err("e.min_samples")
    samples = _samples(status)
    current = engagements.get_settings()["bands"]
    parts, proposal = [], {}
    for fam, fam_parts in scope.DEFAULT_BANDS.items():
        for part in fam_parts:
            mine = [s for s in samples if s["family"] == fam and (s["part"] or "") == part]
            if not mine:
                continue
            vals = [s["per_unit"] for s in mine]
            n = len(vals)
            lo, hi = (quantile(vals, 0.1), quantile(vals, 0.9)) if n >= MIN_SAMPLES else (min(vals), max(vals))
            mean = statistics.fmean(vals)
            sd = statistics.pstdev(vals) if n > 1 else 0.0
            cv = sd / mean if mean else 0.0
            reliability = "insufficient" if n < min_samples else "scattered" if cv > WIDE_CV else "ok"
            band = [_round(lo), _round(max(lo, hi))]
            entry = {"family": fam, "part": part, "n": n, "engagements": len({s["engagement_id"] for s in mine}), "min": _round(min(vals)),
                     "max": _round(max(vals)), "mean": _round(mean), "median": _round(statistics.median(vals)), "stdev": _round(sd),
                     "cv": round(cv, 2), "p10": _round(quantile(vals, 0.1)), "p90": _round(quantile(vals, 0.9)), "proposed": band,
                     "current": list(current[fam][part]), "changes": band != list(current[fam][part]), "reliability": reliability,
                     "note": texts.tr("c.rel." + reliability, n=n, need=min_samples, cv=f"{cv:.0%}")}
            parts.append(entry)
            if reliability != "insufficient" and entry["changes"]:
                proposal.setdefault(fam, {})[part] = band
    return {"status": status, "min_samples": min_samples, "samples": len(samples), "engagements": len({s["engagement_id"] for s in samples}),
            "parts": parts, "bands": proposal, "records": samples[:200], "method": texts.tr("c.method")}
