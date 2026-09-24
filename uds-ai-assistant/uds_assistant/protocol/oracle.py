"""Deterministic UDS "spec oracle".

Given an ECU profile, a protocol state and a request, the oracle computes the
*expected* response (positive pattern, NRC, or "no response") and the next
state. No LLM is involved: this is the rule engine that decides what is correct.

Check order (documented project convention, applied identically everywhere):

    R1  service implemented                         -> 0x11
    R2  service allowed in active session           -> 0x7F
    R3  sub-function byte present (sub-fn services) -> 0x13
    R4  sub-function implemented                    -> 0x12
    R5  sub-function allowed in active session      -> 0x7E
    R6  minimum / format length                     -> 0x13
    R7  identifier lookup (DID / RID / group)       -> 0x31
        (unknown, not readable/writable, or not available in the active session)
    R8  exact message length                        -> 0x13
    R9  security level unlocked                     -> 0x33
    R10 value validity                              -> 0x31
    R11 sequence / conditions                       -> 0x24 / 0x22

Real ECUs may order some of these differently; that is exactly the kind of OEM
detail the profile and the test results are meant to surface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .catalog import SERVICES, SUPPRESS_POSITIVE_RESPONSE
from .nrc import nrc_name
from .profile import ECUProfile


@dataclass
class State:
    session: int = 0x01
    unlocked: set[int] = field(default_factory=set)
    seed_pending: set[int] = field(default_factory=set)
    failed: dict[int, int] = field(default_factory=dict)
    lockout_until: dict[int, int] = field(default_factory=dict)
    now_ms: int = 0
    last_activity_ms: int = 0
    did_values: dict[int, bytes] = field(default_factory=dict)
    dtcs: dict[int, int] = field(default_factory=dict)
    routines: dict[int, str] = field(default_factory=dict)

    def copy(self) -> "State":
        return State(
            session=self.session,
            unlocked=set(self.unlocked),
            seed_pending=set(self.seed_pending),
            failed=dict(self.failed),
            lockout_until=dict(self.lockout_until),
            now_ms=self.now_ms,
            last_activity_ms=self.last_activity_ms,
            did_values=dict(self.did_values),
            dtcs=dict(self.dtcs),
            routines=dict(self.routines),
        )

    def describe(self) -> dict:
        return {
            "session": f"0x{self.session:02X}",
            "unlocked_levels": sorted(self.unlocked),
            "seed_pending": sorted(self.seed_pending),
            "time_ms": self.now_ms,
        }


@dataclass
class Expectation:
    kind: str  # "positive" | "negative" | "none"
    pattern: str = ""  # hex pattern, '??' = wildcard byte
    nrc: Optional[int] = None
    rule: str = ""

    @property
    def nrc_name(self) -> str:
        return nrc_name(self.nrc) if self.nrc is not None else ""


def _pos(pattern: str, rule: str) -> Expectation:
    return Expectation("positive", pattern, None, rule)


def _neg(sid: int, nrc: int, rule: str) -> Expectation:
    return Expectation("negative", f"7F {sid:02X} {nrc:02X}", nrc, rule)


def _hx(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


class SpecOracle:
    def __init__(self, profile: ECUProfile):
        self.p = profile

    # -- state ---------------------------------------------------------------------------------
    def initial_state(self) -> State:
        st = State()
        for d in self.p.dids:
            st.did_values[d.id] = d.default_bytes()
        st.dtcs = {d.code: d.status for d in self.p.dtcs}
        return st

    def advance(self, state: State, ms: int) -> State:
        st = state.copy()
        st.now_ms += ms
        self._expire(st)
        return st

    def _expire(self, st: State) -> None:
        """S3 server timeout: non-default session falls back to default and re-locks."""
        if st.session != 0x01 and st.now_ms - st.last_activity_ms > self.p.timing.s3_ms:
            st.session = 0x01
            st.unlocked.clear()
            st.seed_pending.clear()

    # -- main entry ----------------------------------------------------------------------------
    def step(self, req: bytes, state: State, key_valid: bool = True) -> tuple[Expectation, State]:
        """Evaluate `req` in `state`; return (expectation, next_state)."""
        if not req:
            raise ValueError("empty request")
        st = state.copy()
        self._expire(st)
        st.last_activity_ms = st.now_ms
        exp = self._dispatch(req, st, key_valid)
        return exp, st

    def _dispatch(self, req: bytes, st: State, key_valid: bool) -> Expectation:
        p = self.p
        sid = req[0]
        svc = p.services.get(sid)
        if svc is None:
            return _neg(sid, 0x11, f"R1: service 0x{sid:02X} is not implemented by {p.name}")
        if st.session not in svc.sessions:
            return _neg(sid, 0x7F,
                        f"R2: {svc.name} is not available in {p.session_name(st.session)} "
                        f"(allowed: {', '.join(p.session_name(s) for s in svc.sessions)})")
        info = SERVICES.get(sid)
        sub: Optional[int] = None
        suppress = False
        if info and info.has_subfunction:
            if len(req) < 2:
                return _neg(sid, 0x13, "R3: sub-function byte is missing")
            sub = req[1] & 0x7F
            suppress = bool(req[1] & SUPPRESS_POSITIVE_RESPONSE)
            if sub not in svc.subfunctions:
                return _neg(sid, 0x12, f"R4: sub-function 0x{sub:02X} is not implemented for {svc.name}")
            sd = svc.subfunctions[sub]
            if sd.sessions is not None and st.session not in sd.sessions:
                return _neg(sid, 0x7E, f"R5: sub-function {sd.name} is not available in "
                                       f"{p.session_name(st.session)}")
        handler = getattr(self, f"_svc_{sid:02X}", None)
        if handler is None:
            return _neg(sid, 0x11, f"R1: no behaviour model for service 0x{sid:02X}")
        exp = handler(req, sub, st, key_valid)
        if exp.kind == "positive" and suppress:
            return Expectation("none", "", None, exp.rule + " [suppressPositiveResponse bit set: no reply]")
        return exp

    # -- service models ------------------------------------------------------------------------
    def _svc_10(self, req, sub, st, key_valid):
        if len(req) != 2:
            return _neg(0x10, 0x13, f"R6: DiagnosticSessionControl request must be 2 bytes, got {len(req)}")
        t = self.p.timing
        p2 = t.p2_ms.to_bytes(2, "big")
        p2s = (t.p2_star_ms // 10).to_bytes(2, "big")
        st.session = sub
        st.unlocked.clear()
        st.seed_pending.clear()
        return _pos(f"50 {sub:02X} {_hx(p2)} {_hx(p2s)}",
                    f"session -> {self.p.session_name(sub)}; security re-locked; timing P2={t.p2_ms} ms, "
                    f"P2*={t.p2_star_ms} ms")

    def _svc_11(self, req, sub, st, key_valid):
        if len(req) != 2:
            return _neg(0x11, 0x13, f"R6: ECUReset request must be 2 bytes, got {len(req)}")
        st.session = 0x01
        st.unlocked.clear()
        st.seed_pending.clear()
        st.routines.clear()
        return _pos(f"51 {sub:02X}", "reset accepted; ECU returns to default session, security re-locked")

    def _svc_14(self, req, sub, st, key_valid):
        if len(req) != 4:
            return _neg(0x14, 0x13, f"R6: ClearDiagnosticInformation request must be 4 bytes, got {len(req)}")
        group = int.from_bytes(req[1:4], "big")
        if group == 0xFFFFFF:
            st.dtcs.clear()
        elif group in st.dtcs or group in {d.code for d in self.p.dtcs}:
            st.dtcs.pop(group, None)
        else:
            return _neg(0x14, 0x31, f"R7: DTC group 0x{group:06X} is not supported")
        return _pos("54", f"DTC group 0x{group:06X} cleared")

    def _svc_19(self, req, sub, st, key_valid):
        want = 2 if sub == 0x0A else 3
        if len(req) != want:
            return _neg(0x19, 0x13, f"R6: ReadDTCInformation sub 0x{sub:02X} needs {want} bytes, got {len(req)}")
        avail = 0xFF
        if sub == 0x0A:
            rows = list(st.dtcs.items())
        else:
            mask = req[2]
            rows = [(c, s) for c, s in st.dtcs.items() if s & mask]
        if sub == 0x01:
            return _pos(f"59 01 {avail:02X} 01 {len(rows) >> 8:02X} {len(rows) & 0xFF:02X}",
                        f"{len(rows)} DTC(s) match status mask 0x{req[2]:02X}")
        body = "".join(f" {_hx(c.to_bytes(3, 'big'))} {s:02X}" for c, s in rows)
        return _pos(f"59 {sub:02X} {avail:02X}{body}", f"{len(rows)} DTC record(s) returned")

    def _svc_22(self, req, sub, st, key_valid):
        body = req[1:]
        if len(body) < 2 or len(body) % 2:
            return _neg(0x22, 0x13, f"R6: ReadDataByIdentifier needs 1..n two-byte DIDs, got {len(body)} byte(s)")
        ids = [int.from_bytes(body[i:i + 2], "big") for i in range(0, len(body), 2)]
        defs = []
        for i in ids:
            d = self.p.did(i)
            if d is None or d.read is None:
                return _neg(0x22, 0x31, f"R7: DID 0x{i:04X} is not supported for reading")
            if st.session not in d.read.sessions:
                return _neg(0x22, 0x31, f"R7: DID 0x{i:04X} ({d.name}) is not readable in "
                                        f"{self.p.session_name(st.session)}")
            defs.append(d)
        for d in defs:
            if d.read.security is not None and d.read.security not in st.unlocked:
                return _neg(0x22, 0x33, f"R9: DID 0x{d.id:04X} ({d.name}) needs security level {d.read.security}")
        out = "62"
        for d in defs:
            value = bytes([st.session]) if d.live == "active_session" else st.did_values[d.id]
            out += f" {d.id >> 8:02X} {d.id & 0xFF:02X} {_hx(value)}"
        return _pos(out, "DID data returned: " + ", ".join(d.name for d in defs))

    def _svc_27(self, req, sub, st, key_valid):
        lvl, kind = self.p.security_by_sub(sub)
        if lvl is None:
            return _neg(0x27, 0x12, f"R4: sub-function 0x{sub:02X} is not a configured security level")
        if kind == "seed":
            if len(req) != 2:
                return _neg(0x27, 0x13, f"R6: requestSeed must be 2 bytes, got {len(req)}")
            until = st.lockout_until.get(lvl.level, 0)
            if until > st.now_ms:
                return _neg(0x27, 0x37, f"R11: level {lvl.level} lock-out delay running "
                                        f"({until - st.now_ms} ms left)")
            if until and until <= st.now_ms:
                st.lockout_until.pop(lvl.level, None)
                st.failed[lvl.level] = 0
            if lvl.level in st.unlocked:
                return _pos(f"67 {sub:02X} " + " ".join(["00"] * lvl.seed_length),
                            f"level {lvl.level} already unlocked: all-zero seed")
            st.seed_pending.add(lvl.level)
            return _pos(f"67 {sub:02X} " + " ".join(["??"] * lvl.seed_length), "seed issued")
        # sendKey
        if len(req) != 2 + lvl.key_length:
            return _neg(0x27, 0x13, f"R6: sendKey must be {2 + lvl.key_length} bytes, got {len(req)}")
        if lvl.level not in st.seed_pending:
            return _neg(0x27, 0x24, f"R11: sendKey for level {lvl.level} without a preceding requestSeed")
        st.seed_pending.discard(lvl.level)
        if key_valid:
            st.unlocked.add(lvl.level)
            st.failed[lvl.level] = 0
            return _pos(f"67 {sub:02X}", f"level {lvl.level} unlocked")
        st.failed[lvl.level] = st.failed.get(lvl.level, 0) + 1
        if st.failed[lvl.level] >= lvl.max_attempts:
            st.lockout_until[lvl.level] = st.now_ms + lvl.lockout_ms
            return _neg(0x27, 0x36, f"R11: attempt limit ({lvl.max_attempts}) reached; locked for "
                                    f"{lvl.lockout_ms} ms")
        return _neg(0x27, 0x35, f"R11: invalid key (attempt {st.failed[lvl.level]} of {lvl.max_attempts})")

    def _svc_28(self, req, sub, st, key_valid):
        if len(req) != 3:
            return _neg(0x28, 0x13, f"R6: CommunicationControl request must be 3 bytes, got {len(req)}")
        if req[2] not in (0x01, 0x02, 0x03):
            return _neg(0x28, 0x31, f"R10: communicationType 0x{req[2]:02X} is invalid (expected 01, 02 or 03)")
        return _pos(f"68 {sub:02X}", "communication control applied")

    def _svc_2E(self, req, sub, st, key_valid):
        if len(req) < 3:
            return _neg(0x2E, 0x13, f"R6: WriteDataByIdentifier needs DID + data, got {len(req)} byte(s)")
        did_id = int.from_bytes(req[1:3], "big")
        d = self.p.did(did_id)
        if d is None or d.write is None:
            return _neg(0x2E, 0x31, f"R7: DID 0x{did_id:04X} is not supported for writing")
        if st.session not in d.write.sessions:
            return _neg(0x2E, 0x31, f"R7: DID 0x{did_id:04X} ({d.name}) is not writable in "
                                    f"{self.p.session_name(st.session)}")
        if len(req) != 3 + d.length:
            return _neg(0x2E, 0x13, f"R8: DID 0x{did_id:04X} data length is {d.length}, got {len(req) - 3}")
        if d.write.security is not None and d.write.security not in st.unlocked:
            return _neg(0x2E, 0x33, f"R9: writing {d.name} needs security level {d.write.security}")
        data = req[3:]
        err = d.value_error(data)
        if err:
            return _neg(0x2E, 0x31, f"R10: {err}")
        st.did_values[did_id] = data
        return _pos(f"6E {did_id >> 8:02X} {did_id & 0xFF:02X}", f"{d.name} written")

    def _svc_31(self, req, sub, st, key_valid):
        if len(req) < 4:
            return _neg(0x31, 0x13, f"R6: RoutineControl needs sub-function + RID, got {len(req)} byte(s)")
        rid = int.from_bytes(req[2:4], "big")
        r = self.p.routine(rid)
        if r is None:
            return _neg(0x31, 0x31, f"R7: RID 0x{rid:04X} is not supported")
        if st.session not in r.sessions:
            return _neg(0x31, 0x31, f"R7: RID 0x{rid:04X} ({r.name}) is not available in "
                                    f"{self.p.session_name(st.session)}")
        if sub not in r.subfunctions:
            return _neg(0x31, 0x12, f"R4: routine {r.name} does not implement sub-function 0x{sub:02X}")
        want = 4 + (r.option_length if sub == 1 else 0)
        if len(req) != want:
            return _neg(0x31, 0x13, f"R8: RoutineControl sub 0x{sub:02X} for {r.name} needs {want} bytes, "
                                    f"got {len(req)}")
        if r.security is not None and r.security not in st.unlocked:
            return _neg(0x31, 0x33, f"R9: routine {r.name} needs security level {r.security}")
        cur = st.routines.get(rid)
        if sub == 1:
            if r.single_instance and cur == "running":
                return _neg(0x31, 0x22, f"R11: routine {r.name} is already running")
            st.routines[rid] = "running"
        elif sub == 2:
            if cur != "running":
                return _neg(0x31, 0x24, f"R11: stopRoutine for {r.name} but it was not started")
            st.routines[rid] = "stopped"
        else:
            if cur is None:
                return _neg(0x31, 0x24, f"R11: requestRoutineResults for {r.name} but it was never started")
        tail = r.resp_bytes(sub)
        return _pos(f"71 {sub:02X} {rid >> 8:02X} {rid & 0xFF:02X}" + (f" {_hx(tail)}" if tail else ""),
                    f"routine {r.name}: {['', 'started', 'stopped', 'results returned'][sub]}")

    def _svc_3E(self, req, sub, st, key_valid):
        if len(req) != 2:
            return _neg(0x3E, 0x13, f"R6: TesterPresent request must be 2 bytes, got {len(req)}")
        return _pos("7E 00", "S3 timer restarted")

    def _svc_85(self, req, sub, st, key_valid):
        if len(req) != 2:
            return _neg(0x85, 0x13, f"R6: ControlDTCSetting request must be 2 bytes, got {len(req)}")
        return _pos(f"C5 {sub:02X}", "DTC setting changed")
