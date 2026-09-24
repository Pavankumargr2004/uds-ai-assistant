"""Resolve free text to ECU-profile objects (DIDs, routines, sessions, services).

Everything returned here is looked up in the ECU profile, so text can never invent an identifier.
An optional LLM may *suggest* additional targets; they are kept only if they exist in the profile.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from ..llm.base import LLMClient, LLMUnavailable
from ..protocol.profile import DidDef, ECUProfile, RoutineDef

_GENERIC = {"data", "by", "identifier", "control", "session", "diagnostic"}


def _words(name: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name)]


def _name_match(name: str, text_l: str) -> Optional[int]:
    """Return the text position of `name` if all its significant words occur, else None."""
    words = [w for w in _words(name) if w not in _GENERIC] or _words(name)
    pos = []
    for w in words:
        m = re.search(rf"\b{re.escape(w)}", text_l)
        if not m:
            return None
        pos.append(m.start())
    return min(pos)


def find_dids(p: ECUProfile, text: str) -> list[DidDef]:
    tl = text.lower()
    found: dict[int, int] = {}
    for m in re.finditer(r"(?:0x)?\b([0-9a-f]{4})\b", tl):
        d = p.did(int(m.group(1), 16))
        if d and (m.group(0).startswith("0x") or re.search(r"[a-f]", m.group(1)) or "did" in tl):
            found.setdefault(d.id, m.start())
    for d in p.dids:
        pos = _name_match(d.name, tl)
        if pos is not None:
            found.setdefault(d.id, pos)
    return [p.did(i) for i, _ in sorted(found.items(), key=lambda kv: kv[1])]


def find_routines(p: ECUProfile, text: str) -> list[RoutineDef]:
    tl = text.lower()
    found: dict[int, int] = {}
    for m in re.finditer(r"(?:0x)?\b([0-9a-f]{4})\b", tl):
        r = p.routine(int(m.group(1), 16))
        if r and (m.group(0).startswith("0x") or re.search(r"[a-f]", m.group(1)) or "routine" in tl):
            found.setdefault(r.id, m.start())
    for r in p.routines:
        pos = _name_match(r.name, tl)
        if pos is not None:
            found.setdefault(r.id, pos)
    return [p.routine(i) for i, _ in sorted(found.items(), key=lambda kv: kv[1])]


def find_session(p: ECUProfile, text: str) -> Optional[int]:
    tl = text.lower()
    for sid, name in p.sessions.items():
        key = name.lower().replace("session", "").replace("diagnostic", "")
        if key and re.search(rf"\b{re.escape(key)}", tl):
            return sid
    return None


def find_level(p: ECUProfile, text: str) -> Optional[int]:
    m = re.search(r"\blevel\s*(?:0x)?(\d+)", text.lower())
    if not m:
        return None
    n = int(m.group(1))
    if p.security_level(n):
        return n
    # "level 2" means the 2nd configured level when levels are numbered by sub-function (1, 3, ...)
    if 1 <= n <= len(p.security_levels):
        return p.security_levels[n - 1].level
    return None


SERVICE_WORDS = [
    (0x10, r"\bsession\b|\bdiagnostic mode"),
    (0x11, r"\breset\b|\breboot\b|\brestart\b"),
    (0x14, r"clear.{0,20}(dtc|diagnostic|fault)|erase.{0,10}(dtc|fault)"),
    (0x19, r"\bdtcs?\b|fault (code|memory)|trouble code"),
    (0x22, r"\bread(s|ing)?\b|\breport(s|ing)?\b|\bretriev"),
    (0x27, r"security|\bseed\b|\bkey\b|unlock|authenticat"),
    (0x28, r"communication control|disable (tx|rx|communication)|silence"),
    (0x2E, r"\bwrit(e|es|ing|ten)\b|\bconfigur|\bcalibrat|\bset(s|ting)?\b|\bchang|\bupdat"),
    (0x31, r"routine|self.?test|\bstart(s|ing)?\b.{0,20}\b(test|erase)|\berase"),
    (0x3E, r"tester.?present|keep.?alive|\bs3\b|session timeout"),
    (0x85, r"dtc setting|control dtc|freeze dtc|suppress dtc"),
]


@dataclass
class Intent:
    services: set[int] = field(default_factory=set)
    dids: set[int] = field(default_factory=set)
    routines: set[int] = field(default_factory=set)
    sessions: set[int] = field(default_factory=set)
    negative_only: bool = False
    source: str = "rules"
    notes: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.services or self.dids or self.routines)


def parse_requirement(p: ECUProfile, text: str, llm: Optional[LLMClient] = None) -> Intent:
    tl = text.lower()
    it = Intent()
    it.dids = {d.id for d in find_dids(p, text)}
    it.routines = {r.id for r in find_routines(p, text)}
    s = find_session(p, text)
    if s:
        it.sessions.add(s)
    for sid, rx in SERVICE_WORDS:
        if sid in p.services and re.search(rx, tl):
            it.services.add(sid)
    if it.dids and 0x22 not in it.services and 0x2E not in it.services:
        it.services |= {0x22}
    if it.routines:
        it.services.add(0x31)
    it.negative_only = bool(re.search(r"shall not|must not|reject|invalid|deny|denied|unauthori|refuse|prevent", tl))
    if llm is not None:
        try:
            raw = llm.complete(
                "Extract diagnostic test targets from the requirement. Reply with JSON only: "
                '{"services":[int SIDs],"dids":[int],"routines":[int]}. Use only identifiers that appear in the '
                "requirement text.", text, json_mode=True)
            data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            added = 0
            for sid in data.get("services", []):
                if isinstance(sid, int) and sid in p.services and sid not in it.services:
                    it.services.add(sid); added += 1
            for d in data.get("dids", []):
                if isinstance(d, int) and p.did(d) and d not in it.dids:
                    it.dids.add(d); added += 1
            for r in data.get("routines", []):
                if isinstance(r, int) and p.routine(r) and r not in it.routines:
                    it.routines.add(r); added += 1
            it.source = "rules+llm"
            if added:
                it.notes.append(f"LLM suggested {added} additional target(s), validated against the ECU profile.")
        except (LLMUnavailable, ValueError, AttributeError, json.JSONDecodeError):
            it.notes.append("LLM unavailable or returned invalid JSON; rule-based parsing used.")
    return it


def select_tests(p: ECUProfile, tests, it: Intent):
    """Pick the tests of the full suite that are relevant to the intent."""
    levels: set[int] = set()
    for did in it.dids:
        d = p.did(did)
        for acc in (d.read, d.write):
            if acc and acc.security is not None:
                levels.add(acc.security)
    for rid in it.routines:
        r = p.routine(rid)
        if r.security is not None:
            levels.add(r.security)
    out = []
    for t in tests:
        tg = set(t.targets)
        hit = False
        obj_hit = any(f"did:0x{d:04X}" in tg for d in it.dids) or any(f"rid:0x{r:04X}" in tg for r in it.routines)
        if it.dids or it.routines:
            if obj_hit:
                svc_filter = {s for s in it.services if s != 0x27} or None
                hit = svc_filter is None or t.service in svc_filter or t.service == 0x10
            elif 0x27 in it.services and t.service == 0x27 and any(f"level:{l}" in tg for l in levels):
                hit = True
        else:
            hit = t.service in it.services
        if hit and it.negative_only and t.category == "positive":
            hit = False
        if hit:
            out.append(t)
    return out
