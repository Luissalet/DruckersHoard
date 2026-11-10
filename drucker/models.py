"""Validated shapes. People, Ledger and Atlas keep their own data; here only references to them."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ITEM_KINDS = ("scope", "milestone", "material", "decision", "payment", "assumption", "question", "effort")
ENGAGEMENT_TYPES = ("general", "report", "data", "design", "training")
OPTIONS = ("include", "change_order", "defer", "specify")
# the part of each band family that a real-hours record measures when it does not say
DEFAULT_PART = {"format": "per_deliverable", "content": "base", "pipeline": "base", "quantity": "per_unit"}
EFFORT_PARTS = {"format": ("per_deliverable",), "content": ("base", "per_deliverable"), "pipeline": ("base", "per_extra"), "quantity": ("per_unit",)}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Ref(Strict):
    """Pointer to a record another Hoard owns (app: people, ledger, atlas...)."""
    app: str = Field(min_length=1, max_length=40)
    id: str = Field(min_length=1, max_length=200)
    label: str = ""


def _iso(value):
    if value in (None, ""):
        return None
    date.fromisoformat(value)
    return value


class EngagementIn(Strict):
    name: str = Field(min_length=1, max_length=200)
    client_name: str = Field(default="", max_length=200)
    client_ref: Optional[Ref] = None
    origin: str = Field(default="", max_length=2000)
    status: Literal["lead", "active", "paused", "closed"] = "lead"
    currency: str = Field(default="EUR", pattern=r"^[A-Za-z]{3}$")
    budget_min: Optional[float] = Field(default=None, ge=0)
    budget_max: Optional[float] = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=10000)
    denylist: Optional[list[str]] = None
    kind: Literal["general", "report", "data", "design", "training"] = "general"

    @model_validator(mode="after")
    def _budget(self):
        if self.budget_min is not None and self.budget_max is not None and self.budget_min > self.budget_max:
            raise ValueError("budget_min must not be above budget_max")
        self.currency = self.currency.upper()
        return self


class Scope(Strict):
    title: str = Field(min_length=1, max_length=300)
    detail: str = ""
    status: Literal["proposed", "agreed", "done", "dropped"] = "proposed"
    origin: Literal["initial", "agreement", "change"] = "initial"
    deliverable: str = ""


class Milestone(Strict):
    title: str = Field(min_length=1, max_length=300)
    due: Optional[str] = None
    status: Literal["planned", "in_progress", "done", "late", "blocked"] = "planned"
    note: str = ""
    @field_validator("due")
    @classmethod
    def _date_due(cls, v):
        return _iso(v)


class Material(Strict):
    title: str = Field(min_length=1, max_length=300)
    kind: Literal["atlas", "path", "url", "note"] = "path"
    ref: str = Field(default="", max_length=2000)
    atlas: Optional[Ref] = None
    note: str = ""


class HourRange(Strict):
    min: float = Field(ge=0, le=100000)
    max: float = Field(ge=0, le=100000)

    @model_validator(mode="after")
    def _order(self):
        if self.min > self.max:
            raise ValueError("min must not be above max")
        return self


class MoneyRange(HourRange):
    currency: str = Field(default="EUR", pattern=r"^[A-Za-z]{3}$")


class Decision(Strict):
    """A note in the decision log. When it records the commercial option chosen for a scope request, ``option`` says which
    (include, change order, defer, specify) and ``hours`` / ``money`` keep the range that was on the table."""
    what: str = Field(min_length=1, max_length=1000)
    why: str = ""
    date: Optional[str] = None
    who: str = ""
    option: Optional[Literal["include", "change_order", "defer", "specify"]] = None
    request: str = Field(default="", max_length=1000)
    hours: Optional[HourRange] = None
    money: Optional[MoneyRange] = None

    @field_validator("hours", "money", mode="before")
    @classmethod
    def _range_forms(cls, v):
        """A range may come as {min, max}, as [min, max] or as a single number (both ends the same)."""
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return {"min": v, "max": v}
        if isinstance(v, (list, tuple)) and len(v) == 2:
            return {"min": v[0], "max": v[1]}
        return v

    @field_validator("date")
    @classmethod
    def _date_date(cls, v):
        return _iso(v)


class Payment(Strict):
    title: str = Field(min_length=1, max_length=300)
    kind: Literal["invoice", "payment"] = "invoice"
    amount: Optional[float] = Field(default=None, ge=0)
    currency: str = Field(default="EUR", pattern=r"^[A-Za-z]{3}$")
    date: Optional[str] = None
    status: Literal["planned", "issued", "paid", "overdue"] = "planned"
    ledger: Optional[Ref] = None
    source: Literal["ledger", "manual"] = "manual"
    @field_validator("date")
    @classmethod
    def _date_date(cls, v):
        return _iso(v)

    @model_validator(mode="after")
    def _source(self):
        # Money movements live in Ledger; an entry without a Ledger reference is always marked manual.
        self.source = "ledger" if self.ledger else "manual"
        self.currency = self.currency.upper()
        return self


class Assumption(Strict):
    text: str = Field(min_length=1, max_length=1000)


class Question(Strict):
    text: str = Field(min_length=1, max_length=1000)
    status: Literal["open", "answered"] = "open"
    answer: str = ""


class Effort(Strict):
    """Real hours spent on one kind of work in this engagement. Closed engagements feed the proposed effort bands:
    ``hours`` / ``units`` is the sample (hours per deliverable, per unit or for the whole job)."""
    title: str = Field(min_length=1, max_length=300)
    family: Literal["format", "content", "pipeline", "quantity"]
    part: Optional[Literal["base", "per_deliverable", "per_extra", "per_unit"]] = None
    hours: float = Field(gt=0, le=100000)
    units: float = Field(default=1, gt=0, le=100000)
    note: str = ""

    @model_validator(mode="after")
    def _part(self):
        if self.part is None:
            self.part = DEFAULT_PART[self.family]
        elif self.part not in EFFORT_PARTS[self.family]:
            raise ValueError(f"part {self.part} does not belong to family {self.family}")
        return self


ITEM_MODELS = {"scope": Scope, "milestone": Milestone, "material": Material, "decision": Decision,
               "payment": Payment, "assumption": Assumption, "question": Question, "effort": Effort}
