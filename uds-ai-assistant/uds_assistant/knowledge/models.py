from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from pydantic import BaseModel

LAYERS = ("standard", "oem", "ecu", "project")  # separate collections per knowledge layer


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    section: str = ""
    page: Optional[int] = None
    layer: str = "project"
    project: str = ""
    version: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Chunk":
        return cls(**d)

    @property
    def location(self) -> str:
        loc = self.source
        if self.section:
            loc += f" > {self.section}"
        if self.page is not None:
            loc += f" (p.{self.page})"
        return loc


class CitationOut(BaseModel):
    n: int
    source: str
    section: str = ""
    page: Optional[int] = None
    layer: str = ""
    version: str = ""
    chunk_id: str = ""
    snippet: str = ""
    score: float = 0.0


class Answer(BaseModel):
    question: str
    answer: str
    mode: str                       # "llm" | "extractive" | "no_evidence"
    confidence: float = 0.0
    confidence_label: str = "insufficient"   # high | medium | low | insufficient
    citations: list[CitationOut] = []
    warnings: list[str] = []
