"""Coverage model: what *could* be tested for a profile vs. what generated tests cover.

Every test declares ``covers`` keys. The universe is derived from the ECU profile
independently of any test, so gaps are real.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .generator.models import TestCase
from .protocol.catalog import SERVICES
from .protocol.profile import ECUProfile

# -- key constructors (shared with the generator) ---------------------------------------------
def k_sub(sid: int, sub: int) -> str: return f"{sid:02X}/sub{sub:02X}/pos"
def k_nrc(sid: int, nrc: int) -> str: return f"{sid:02X}/nrc{nrc:02X}"
def k_did(sid: int, did: int, aspect: str) -> str: return f"{sid:02X}/did{did:04X}/{aspect}"
def k_rid(rid: int, aspect: str) -> str: return f"31/rid{rid:04X}/{aspect}"
def k_misc(sid: int, name: str) -> str: return f"{sid:02X}/{name}"

SECURITY_NRCS = {0x24, 0x33, 0x35, 0x36, 0x37}
SESSION_NRCS = {0x7E, 0x7F}


def _nrc_category(sid: int, nrc: int) -> str:
    if nrc in SECURITY_NRCS and (nrc != 0x24 or sid == 0x27):
        return "security"
    if nrc in SESSION_NRCS:
        return "session"
    return "negative"


def coverage_universe(p: ECUProfile) -> dict[str, str]:
    """Return {coverage key: category}."""
    u: dict[str, str] = {}
    all_sessions = set(p.sessions)
    any_sec_did_read = any(d.read and d.read.security for d in p.dids)
    any_sec_did_write = any(d.write and d.write.security for d in p.dids)
    any_sec_rid = any(r.security for r in p.routines)
    for sid, svc in p.services.items():
        info = SERVICES.get(sid)
        if info is None:
            continue
        for sub in svc.subfunctions:
            u[k_sub(sid, sub)] = "positive"
        nrcs = {0x13}
        if info.has_subfunction:
            nrcs.add(0x12)
        if set(svc.sessions) != all_sessions:
            nrcs.add(0x7F)
        if any(sd.sessions is not None and set(sd.sessions) != set(svc.sessions)
               for sd in svc.subfunctions.values()):
            nrcs.add(0x7E)
        if sid in (0x14, 0x22, 0x28, 0x2E, 0x31):
            nrcs.add(0x31)
        if (sid == 0x22 and any_sec_did_read) or (sid == 0x2E and any_sec_did_write) or \
                (sid == 0x31 and any_sec_rid):
            nrcs.add(0x33)
        if sid == 0x27 and p.security_levels:
            nrcs |= {0x24, 0x35, 0x36, 0x37}
        if sid == 0x31 and p.routines:
            nrcs.add(0x24)
            if any(r.single_instance for r in p.routines):
                nrcs.add(0x22)
        for n in nrcs:
            u[k_nrc(sid, n)] = _nrc_category(sid, n)
    u[k_misc(0x00, "nrc11")] = "negative"

    if 0x22 in p.services:
        for d in p.readable_dids:
            u[k_did(0x22, d.id, "pos")] = "positive"
            if d.read.security is not None:
                u[k_did(0x22, d.id, "sec_denied")] = "security"
            if set(d.read.sessions) != all_sessions and (set(p.services[0x22].sessions) - set(d.read.sessions)):
                u[k_did(0x22, d.id, "wrong_session")] = "session"
        u[k_misc(0x22, "multi")] = "positive"
    if 0x2E in p.services:
        for d in p.writable_dids:
            u[k_did(0x2E, d.id, "pos")] = "positive"
            u[k_did(0x2E, d.id, "bad_length")] = "negative"
            if d.write.security is not None:
                u[k_did(0x2E, d.id, "sec_denied")] = "security"
            if set(p.services[0x2E].sessions) - set(d.write.sessions):
                u[k_did(0x2E, d.id, "wrong_session")] = "session"
            if _invalid_values(d):
                u[k_did(0x2E, d.id, "invalid_value")] = "negative"
    if 0x31 in p.services:
        for r in p.routines:
            u[k_rid(r.id, "pos")] = "positive"
            u[k_rid(r.id, "bad_length")] = "negative"
            u[k_rid(r.id, "seq_error")] = "negative"
            if r.security is not None:
                u[k_rid(r.id, "sec_denied")] = "security"
            if set(p.services[0x31].sessions) - set(r.sessions):
                u[k_rid(r.id, "wrong_session")] = "session"
    if 0x10 in p.services:
        u[k_misc(0x10, "spr")] = "positive"
        if p.security_levels and any(d.write and d.write.security for d in p.dids):
            u[k_misc(0x10, "relock")] = "security"
    if 0x3E in p.services:
        u[k_misc(0x3E, "spr")] = "positive"
        if any(d.live == "active_session" for d in p.dids):
            u[k_misc(0x3E, "s3_timeout")] = "timing"
            u[k_misc(0x3E, "keepalive")] = "timing"
    if 0x27 in p.services and p.security_levels:
        u[k_misc(0x27, "already_unlocked")] = "security"
        u[k_misc(0x27, "lockout_expiry")] = "timing"
    return u


def _invalid_values(d) -> list[bytes]:
    """Values that the DID definition says are invalid (used by generator and universe)."""
    out: list[bytes] = []
    if d.data_type == "uint":
        top = (1 << (8 * d.length)) - 1
        if d.min is not None and d.min > 0:
            out.append((d.min - 1).to_bytes(d.length, "big"))
        if d.max is not None and d.max < top:
            out.append((d.max + 1).to_bytes(d.length, "big"))
    elif d.data_type == "ascii" and d.pattern and d.invalid_example is not None:
        out.append(d.encode(d.invalid_example))
    return out


def compute_coverage(p: ECUProfile, tests: Iterable[TestCase]) -> dict:
    tests = list(tests)
    universe = coverage_universe(p)
    covered_keys: dict[str, list[str]] = defaultdict(list)
    for t in tests:
        for k in t.covers:
            if k in universe:
                covered_keys[k].append(t.id)
    by_cat: dict[str, dict] = defaultdict(lambda: {"total": 0, "covered": 0})
    by_service: dict[str, dict] = defaultdict(lambda: {"total": 0, "covered": 0})
    for k, cat in universe.items():
        sid = int(k.split("/")[0], 16)
        sname = "Global" if sid == 0 else f"0x{sid:02X} {p.services[sid].name}" if sid in p.services else f"0x{sid:02X}"
        for bucket in (by_cat[cat], by_service[sname]):
            bucket["total"] += 1
            bucket["covered"] += 1 if k in covered_keys else 0
    for b in list(by_cat.values()) + list(by_service.values()):
        b["percent"] = round(100.0 * b["covered"] / b["total"], 1) if b["total"] else 100.0
    total, cov = len(universe), len(covered_keys)
    return {
        "total_items": total,
        "covered_items": cov,
        "percent": round(100.0 * cov / total, 1) if total else 100.0,
        "by_category": dict(sorted(by_cat.items())),
        "by_service": dict(sorted(by_service.items())),
        "gaps": sorted(k for k in universe if k not in covered_keys),
        "test_count": len(tests),
    }
