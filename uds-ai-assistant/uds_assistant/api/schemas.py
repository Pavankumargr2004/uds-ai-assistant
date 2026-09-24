"""Request/response bodies for the API that aren't already defined as domain models."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str


class AskRequest(BaseModel):
    question: str
    k: int = 5
    layers: Optional[list[str]] = None


class GenerateRequest(BaseModel):
    requirement: Optional[str] = None   # free text; None = generate the full systematic suite
    use_llm: bool = False


class ReviewRequest(BaseModel):
    decision: str   # approved | rejected | changes_requested
    comment: str = ""


class RunRequest(BaseModel):
    test_ids: Optional[list[str]] = None   # None = every approved test
    target: str = "simulator"              # simulator | hardware
    faults: list[str] = []                 # simulator only, for demos
    hw_interface: Optional[str] = None
    include_draft: bool = False


class ValidateRequest(BaseModel):
    request: str
    session: int = 1
    unlocked: list[int] = []
    seed_requested: list[int] = []


class BuildRequest(BaseModel):
    text: str
