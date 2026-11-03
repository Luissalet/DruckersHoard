"""Validated shapes. People, Ledger and Atlas keep their own data; here only references to them."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ITEM_KINDS = ("scope", "milestone", "material", "decision", "payment", "assumption", "question")


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


class Decision(Strict):
    what: str = Field(min_length=1, max_length=1000)
    why: str = ""
    date: Optional[str] = None
    who: str = ""
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


ITEM_MODELS = {"scope": Scope, "milestone": Milestone, "material": Material, "decision": Decision,
               "payment": Payment, "assumption": Assumption, "question": Question}
