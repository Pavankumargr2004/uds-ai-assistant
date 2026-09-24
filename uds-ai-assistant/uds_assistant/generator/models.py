"""Structured test-case model shared by generator, exporters, runner, API and UI."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Category = Literal["positive", "negative", "session", "security", "timing", "boundary"]
Status = Literal["draft", "approved", "rejected"]


class Step(BaseModel):
    n: int
    role: Literal["setup", "test", "cleanup"] = "test"
    action: Literal["send", "wait"] = "send"
    request: str = ""              # hex, may contain {KEY:<level>} / {BADKEY:<level>} placeholders
    expect: Literal["positive", "negative", "none"] = "positive"
    expected_pattern: str = ""     # hex with '??' wildcard bytes; "" when expect == "none"
    nrc: Optional[int] = None
    wait_ms: int = 0
    description: str = ""
    rule: str = ""                 # oracle rule that justifies the expectation


class Citation(BaseModel):
    source: str
    section: str = ""
    chunk_id: str = ""


class TestCase(BaseModel):
    __test__ = False  # not a pytest class

    id: str
    title: str
    category: Category
    service: int
    objective: str = ""
    requirement_id: Optional[str] = None
    preconditions: list[str] = Field(default_factory=list)
    steps: list[Step]
    pass_criteria: str = ""
    covers: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)   # e.g. ["svc:0x22", "did:0xF190"]
    sources: list[Citation] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    origin: Literal["generated", "requirement", "manual"] = "generated"
    status: Status = "draft"
    created_by: str = ""

    @property
    def sends(self) -> list[Step]:
        return [s for s in self.steps if s.action == "send"]
