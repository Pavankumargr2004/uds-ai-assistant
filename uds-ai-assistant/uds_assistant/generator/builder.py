"""Turn a plain-language instruction into a raw UDS request (rule-based, profile-resolved)."""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from ..protocol.hexutil import parse_hex, to_hex
from ..protocol.profile import DidDef, ECUProfile
from .intent import find_dids, find_level, find_routines, find_session


class BuiltRequest(BaseModel):
    ok: bool
    request: str = ""
    description: str = ""
    notes: list[str] = Field(default_factory=list)
    suggested_session: Optional[int] = None
    suggested_unlocked: list[int] = Field(default_factory=list)


def _sub_by_name(p: ECUProfile, sid: int, *needles: str) -> Optional[int]:
    svc = p.services.get(sid)
    if not svc:
        return None
    for sub, sd in svc.subfunctions.items():
        if any(n in sd.name.lower() for n in needles):
            return sub
    return None


def _value_for(d: DidDef, text: str) -> Optional[bytes]:
    q = re.search(r"['\"]([^'\"]+)['\"]", text)
    tail = re.split(r"\b(?:to|=|with|value|as)\b", text, maxsplit=1, flags=re.I)
    cand = q.group(1) if q else (tail[1].strip() if len(tail) > 1 else "")
    if d.data_type == "uint":
        m = re.search(r"(0x[0-9a-fA-F]+|\d+)", cand or text.split(d.name)[-1])
        if not m:
            return None
        return int(m.group(1), 0).to_bytes(d.length, "big")
    if d.data_type == "ascii":
        val = (cand.split()[0] if cand else "").strip(" .")
        return d.encode(val) if val else None
    m = re.search(r"((?:0x)?[0-9a-fA-F]{2}(?:[ ,]*(?:0x)?[0-9a-fA-F]{2})*)", cand)
    return parse_hex(m.group(1)) if m else None


def build_request(p: ECUProfile, text: str) -> BuiltRequest:
    t = text.strip()
    tl = t.lower()
    if re.fullmatch(r"(?:0x)?[0-9a-fA-F]{2}(?:[\s,]*(?:0x)?[0-9a-fA-F]{2})*", t):
        return BuiltRequest(ok=True, request=to_hex(parse_hex(t)), description="Raw hex request (used as given).")

    def done(req: bytes, desc: str, notes=None, session=None, unlocked=None) -> BuiltRequest:
        return BuiltRequest(ok=True, request=to_hex(req), description=desc, notes=notes or [],
                            suggested_session=session, suggested_unlocked=unlocked or [])

    def fail(msg: str) -> BuiltRequest:
        return BuiltRequest(ok=False, description=msg)

    dids, routines = find_dids(p, t), find_routines(p, t)
    spr = 0x80 if re.search(r"suppress|no response|silent", tl) else 0

    if re.search(r"tester.?present|keep.?alive", tl):
        return done(bytes([0x3E, 0x00 | spr]), "TesterPresent" + (" with suppressPositiveResponse" if spr else ""))
    if re.search(r"dtc setting|control dtc", tl) or (re.search(r"\b(enable|disable|stop|resume)\b.*\bdtc\b", tl) and "clear" not in tl):
        sub = 0x02 if re.search(r"disable|off|stop|freeze", tl) else 0x01
        return done(bytes([0x85, sub]), f"ControlDTCSetting {'off' if sub == 2 else 'on'}", session=0x03)
    if re.search(r"clear.*(dtc|diagnostic|fault)|erase.*(dtc|fault)", tl):
        m = re.search(r"0x([0-9a-fA-F]{6})\b", t)
        group = int(m.group(1), 16) if m else 0xFFFFFF
        return done(bytes([0x14]) + group.to_bytes(3, "big"), f"Clear DTC group 0x{group:06X}")
    if re.search(r"\bdtcs?\b|fault (code|memory)", tl) and not dids:
        m = re.search(r"mask\s*(?:0x)?([0-9a-fA-F]{1,2})\b", tl)
        mask = int(m.group(1), 16) if m else 0xFF
        if re.search(r"count|number|how many", tl):
            return done(bytes([0x19, 0x01, mask]), f"Count DTCs matching status mask 0x{mask:02X}")
        if "support" in tl:
            return done(bytes([0x19, 0x0A]), "List all supported DTCs")
        return done(bytes([0x19, 0x02, mask]), f"Read DTCs matching status mask 0x{mask:02X}")
    if re.search(r"seed|unlock|security|send key|\bkey\b", tl) and not dids and not routines:
        lvl = find_level(p, t) or (p.security_levels[0].level if p.security_levels else None)
        sl = p.security_level(lvl) if lvl is not None else None
        if sl is None:
            return fail("This ECU profile defines no security levels.")
        if re.search(r"send key|\bkey\b", tl) and not re.search(r"seed|unlock", tl):
            return done(bytes([0x27, sl.send_key_sub]) + bytes(sl.key_length),
                        f"Send key for level {sl.level}",
                        ["Key bytes are a placeholder: compute seed XOR constant, or use {KEY:%d} in a test step." % sl.level],
                        session=0x03)
        return done(bytes([0x27, sl.level]), f"Request seed for security level {sl.level}",
                    ["Follow with sendKey (27 %02X <key>) using the seed returned by the ECU." % sl.send_key_sub],
                    session=0x03)
    if re.search(r"communication", tl):
        sub = _sub_by_name(p, 0x28, "disablerxandtx") if re.search(r"disable", tl) else _sub_by_name(p, 0x28, "enablerxandtx")
        if sub is None:
            return fail("CommunicationControl is not implemented by this ECU profile.")
        return done(bytes([0x28, sub, 0x01]), f"CommunicationControl {p.services[0x28].subfunctions[sub].name} (normal messages)",
                    ["Disabling communication interrupts the bus: use only on an isolated bench."], session=0x03)
    if re.search(r"\breset\b|\breboot\b|\brestart\b", tl):
        sub = (_sub_by_name(p, 0x11, "hard") if "hard" in tl else _sub_by_name(p, 0x11, "soft") if "soft" in tl
               else _sub_by_name(p, 0x11, "hard", "soft"))
        if sub is None:
            return fail("ECUReset is not implemented by this ECU profile.")
        return done(bytes([0x11, sub]), f"ECUReset {p.services[0x11].subfunctions[sub].name}", session=0x03)
    if routines and re.search(r"start|run|stop|result|status|erase|test", tl):
        r = routines[0]
        sub = 0x02 if re.search(r"\bstop\b", tl) else 0x03 if re.search(r"result|status", tl) else 0x01
        opt = b""
        if sub == 1 and r.option_length:
            m = re.findall(r"\b(?:0x[0-9a-fA-F]+|\d+)\b", re.sub(r"0x[0-9a-fA-F]{4}\b", "", t))
            opt = (int(m[0], 0) if m else 0).to_bytes(r.option_length, "big")
        return done(bytes([0x31, sub]) + r.id.to_bytes(2, "big") + opt,
                    f"RoutineControl {['', 'start', 'stop', 'requestResults'][sub]} {r.name} (0x{r.id:04X})",
                    session=r.sessions[0], unlocked=[r.security] if r.security else [])
    if dids and re.search(r"\b(write|set|change|update|program|configure)\b", tl):
        d = dids[0]
        if not d.write:
            return fail(f"DID 0x{d.id:04X} {d.name} is not writable in this ECU profile.")
        val = _value_for(d, t)
        if val is None:
            return fail(f"No value found for {d.name}; expected {d.length} byte(s) of {d.data_type} data, e.g. \"write {d.name} to <value>\".")
        return done(bytes([0x2E]) + d.id.to_bytes(2, "big") + val, f"Write {d.name} (0x{d.id:04X})",
                    session=d.write.sessions[0], unlocked=[d.write.security] if d.write.security else [])
    if dids:
        req = bytes([0x22]) + b"".join(d.id.to_bytes(2, "big") for d in dids)
        d0 = dids[0]
        return done(req, "Read " + ", ".join(f"{d.name} (0x{d.id:04X})" for d in dids),
                    session=d0.read.sessions[0] if d0.read else None,
                    unlocked=[d0.read.security] if d0.read and d0.read.security else [])
    s = find_session(p, t)
    if s is not None:
        return done(bytes([0x10, s | spr]), f"DiagnosticSessionControl -> {p.session_name(s)}")
    return fail("Could not map the instruction to a request for this ECU. Name a DID/routine, a session, "
                "'read DTCs', 'request seed', or enter raw hex such as '22 F1 90'.")
