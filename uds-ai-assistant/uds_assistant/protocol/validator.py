"""Validate a raw UDS request against the ECU profile and explain the expected response."""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from .catalog import SERVICES, SUPPRESS_POSITIVE_RESPONSE
from .hexutil import parse_hex, to_hex
from .nrc import NRC_HINTS, nrc_name
from .oracle import SpecOracle
from .profile import ECUProfile

STATE_CHANGING = {0x10: "changes the diagnostic session and re-locks security", 0x11: "resets the ECU",
                  0x14: "erases stored DTCs", 0x28: "changes CAN communication behaviour",
                  0x2E: "writes non-volatile data", 0x31: "starts/stops an ECU routine",
                  0x85: "changes DTC recording"}


class Finding(BaseModel):
    level: str  # info | warning | error
    message: str


class ValidationReport(BaseModel):
    request: str
    valid_hex: bool = True
    service: Optional[int] = None
    service_name: str = ""
    sub_function: Optional[int] = None
    suppress_bit: bool = False
    expectation: str = ""            # positive | negative | none
    expected_pattern: str = ""
    nrc: Optional[int] = None
    nrc_name: str = ""
    rule: str = ""
    findings: list[Finding] = Field(default_factory=list)
    state_before: dict = Field(default_factory=dict)
    state_after: dict = Field(default_factory=dict)


def validate_request(p: ECUProfile, text: str, session: int = 0x01, unlocked: Optional[list[int]] = None,
                     seed_requested: Optional[list[int]] = None) -> ValidationReport:
    rep = ValidationReport(request=text.strip())
    key_valid = True
    key_ph = re.search(r"\{(KEY|BADKEY):(\d+)\}", text)
    if key_ph:
        key_valid = key_ph.group(1) == "KEY"
        lvl = p.security_level(int(key_ph.group(2)))
        text = re.sub(r"\{(KEY|BADKEY):\d+\}", to_hex(bytes(lvl.key_length)) if lvl else "", text)
    try:
        req = parse_hex(text)
    except ValueError as e:
        rep.valid_hex = False
        rep.findings.append(Finding(level="error", message=str(e)))
        return rep
    if not req:
        rep.valid_hex = False
        rep.findings.append(Finding(level="error", message="Request is empty."))
        return rep
    rep.request = to_hex(req)
    sid = req[0]
    rep.service = sid
    info = SERVICES.get(sid)
    rep.service_name = info.name if info else (p.services[sid].name if sid in p.services else f"0x{sid:02X}")
    if info:
        rep.findings.append(Finding(level="info", message=f"{info.name}: request format `{info.request_format}`."))
        if info.has_subfunction and len(req) > 1:
            rep.sub_function = req[1] & 0x7F
            rep.suppress_bit = bool(req[1] & SUPPRESS_POSITIVE_RESPONSE)
            svc = p.services.get(sid)
            sd = svc.subfunctions.get(rep.sub_function) if svc else None
            if sd:
                rep.findings.append(Finding(level="info", message=f"Sub-function 0x{rep.sub_function:02X} = {sd.name}."))
            if rep.suppress_bit:
                rep.findings.append(Finding(level="info", message="Bit 7 (suppressPositiveResponse) is set: "
                                            "no positive response will be sent."))
    else:
        rep.findings.append(Finding(level="warning", message="Service is not in the generic UDS catalogue of this tool."))
    oracle = SpecOracle(p)
    st = oracle.initial_state()
    st.session = session
    st.unlocked = set(unlocked or [])
    st.seed_pending = set(seed_requested or [])
    rep.state_before = st.describe()
    exp, after = oracle.step(req, st, key_valid=key_valid)
    rep.state_after = after.describe()
    rep.expectation, rep.expected_pattern, rep.nrc, rep.rule = exp.kind, exp.pattern, exp.nrc, exp.rule
    rep.nrc_name = nrc_name(exp.nrc) if exp.nrc is not None else ""
    if exp.nrc is not None:
        rep.findings.append(Finding(level="error", message=f"Expected negative response 0x{exp.nrc:02X} "
                                    f"{rep.nrc_name}. {NRC_HINTS.get(exp.nrc, '')}".strip()))
    if exp.kind == "positive" and sid in STATE_CHANGING:
        rep.findings.append(Finding(level="warning", message=f"This request {STATE_CHANGING[sid]}. "
                                    "Do not run it against a vehicle or bench ECU without approval."))
    if sid == 0x27 and rep.sub_function is not None:
        lv, kind = p.security_by_sub(rep.sub_function)
        if kind == "key":
            rep.findings.append(Finding(level="warning", message="The key value cannot be verified without the seed; "
                                        "the expectation assumes a correct key (use {BADKEY:n} to model a wrong one)."))
    return rep
