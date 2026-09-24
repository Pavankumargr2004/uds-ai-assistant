"""Deterministic test-suite generation from an ECU profile.

Every expected value is produced by the spec oracle while a Scenario is being
built, so tests are correct by construction with respect to the profile.
The LLM is never asked for expected results.
"""
from __future__ import annotations

from typing import Callable, Optional

from ..coverage import _invalid_values, k_did, k_misc, k_nrc, k_rid, k_sub
from ..protocol.catalog import PROBE_UNSUPPORTED_SIDS, SERVICES
from ..protocol.oracle import SpecOracle
from ..protocol.profile import DidDef, ECUProfile, RoutineDef
from .models import TestCase
from .scenario import Scenario

UNUSED_SUBS = (0x55, 0x40, 0x0F, 0x7D, 0x21)
UNUSED_DID = 0xBEEF
UNUSED_RID = 0xBEEF


def _b(*vals: int) -> bytes:
    return bytes(vals)


def _did_bytes(did: int) -> bytes:
    return did.to_bytes(2, "big")


class SuiteBuilder:
    def __init__(self, profile: ECUProfile):
        self.p = profile
        self.o = SpecOracle(profile)
        self.tests: list[TestCase] = []
        self._counters: dict[int, int] = {}
        self.session_did: Optional[DidDef] = next((d for d in profile.dids if d.live == "active_session"), None)

    # ------------------------------------------------------------------------------------------
    def build(self) -> list[TestCase]:
        self.tests = []
        self._counters = {}
        gens: list[Callable[[], None]] = [
            self.gen_global, self.gen_10, self.gen_11, self.gen_14, self.gen_19, self.gen_22,
            self.gen_27, self.gen_28, self.gen_2E, self.gen_31, self.gen_3E, self.gen_85,
        ]
        for g in gens:
            g()
        return self.tests

    # -- helpers ------------------------------------------------------------------------------
    def sc(self) -> Scenario:
        return Scenario(self.o)

    def _pick(self, sessions: list[int]) -> Optional[int]:
        if not sessions:
            return None
        return 0x03 if 0x03 in sessions else sessions[0]

    def _svc_sessions(self, sid: int) -> list[int]:
        return self.p.services[sid].sessions if sid in self.p.services else []

    def _unused_sub(self, sid: int) -> int:
        return next(s for s in UNUSED_SUBS if s not in self.p.services[sid].subfunctions)

    def _other_session(self, allowed: list[int]) -> Optional[int]:
        """A profile session that is NOT in `allowed`."""
        cands = [s for s in self.p.sessions if s not in allowed]
        return cands[0] if cands else None

    def _secure_session(self, access_sessions: list[int], sid: int, level: Optional[int]) -> Optional[int]:
        """Session usable for service `sid` on an object with `access_sessions`; if a security level is
        required the session must also allow SecurityAccess (session changes re-lock the ECU)."""
        ok = [s for s in access_sessions if s in self._svc_sessions(sid)]
        if level is not None:
            ok = [s for s in ok if s in self._svc_sessions(0x27)]
        return self._pick(ok)

    def add(self, sid: int, title: str, category: str, sc: Scenario, objective: str,
            covers: list[str], targets: list[str], pass_criteria: str = "") -> TestCase:
        n = self._counters.get(sid, 0) + 1
        self._counters[sid] = n
        pre = [s.description for s in sc.steps if s.role == "setup"]
        tc = TestCase(
            id=f"TC-{sid:02X}-{n:03d}", title=title, category=category, service=sid,
            objective=objective, preconditions=pre, steps=sc.steps,
            pass_criteria=pass_criteria or "Every step returns the expected response (see expected_pattern).",
            covers=sorted(set(covers)), targets=sorted(set([f"svc:0x{sid:02X}"] + targets)),
            tags=[category, self.p.services[sid].name if sid in self.p.services else "global"],
        )
        self.tests.append(tc)
        return tc

    def _read_session_did(self, sc: Scenario, expected_note: str = "") -> None:
        if self.session_did:
            sc.send(_b(0x22) + _did_bytes(self.session_did.id),
                    f"Read active session (DID 0x{self.session_did.id:04X}) {expected_note}".strip())

    def _wrong_session_case(self, sid: int, req: bytes, what: str, extra_cover: Optional[list[str]] = None) -> None:
        if sid not in self.p.services:
            return
        other = self._other_session(self._svc_sessions(sid))
        if other is None:
            return
        sc = self.sc()
        sc.enter(other)
        sc.send(req, f"{what} in {self.p.session_name(other)}")
        self.add(sid, f"{self.p.services[sid].name} rejected in {self.p.session_name(other)}", "session", sc,
                 f"Service 0x{sid:02X} must not be available in {self.p.session_name(other)}.",
                 [k_nrc(sid, 0x7F)] + (extra_cover or []), [f"session:0x{other:02X}"])

    def _length_cases(self, sid: int, bad_reqs: list[tuple[bytes, str]], session: Optional[int] = None,
                      extra: Optional[list[str]] = None, targets: Optional[list[str]] = None,
                      title: str = "incorrect message length") -> None:
        sc = self.sc()
        sess = session if session is not None else self._pick(self._svc_sessions(sid))
        if sess:
            sc.enter(sess)
        for req, desc in bad_reqs:
            sc.send(req, desc)
        self.add(sid, f"{self.p.services[sid].name}: {title}", "negative", sc,
                 "Malformed lengths must be rejected with NRC 0x13.",
                 [k_nrc(sid, 0x13)] + (extra or []), targets or [])

    def _unsupported_sub_case(self, sid: int, build: Callable[[int], bytes]) -> None:
        sc = self.sc()
        sess = self._pick(self._svc_sessions(sid))
        if sess:
            sc.enter(sess)
        sub = self._unused_sub(sid)
        sc.send(build(sub), f"Send unsupported sub-function 0x{sub:02X}")
        self.add(sid, f"{self.p.services[sid].name}: unsupported sub-function", "negative", sc,
                 "An unimplemented sub-function must be rejected with NRC 0x12.", [k_nrc(sid, 0x12)], [])

    # ------------------------------------------------------------------------------------------
    def gen_global(self) -> None:
        sid = next((s for s in PROBE_UNSUPPORTED_SIDS if s not in self.p.services), None)
        if sid is None:
            return
        sc = self.sc()
        sc.send(_b(sid, 0x01), f"Send unimplemented service 0x{sid:02X}")
        tc = TestCase(
            id="TC-00-001", title="Unimplemented service is rejected", category="negative", service=0,
            objective="Services the ECU does not implement must answer NRC 0x11.", steps=sc.steps,
            pass_criteria="ECU answers 7F <SID> 11.", covers=[k_misc(0, "nrc11")],
            targets=["svc:global"], tags=["negative", "global"])
        self.tests.append(tc)

    # -- 0x10 ---------------------------------------------------------------------------------
    def gen_10(self) -> None:
        sid = 0x10
        if sid not in self.p.services:
            return
        svc = self.p.services[sid]
        for sub, sd in svc.subfunctions.items():
            sc = self.sc()
            if sub == 0x01 and 0x03 in self._svc_sessions(sid):
                sc.enter(0x03)
            sc.send(_b(sid, sub), f"Request {sd.name}")
            if self.session_did:
                self._read_session_did(sc, "(must equal the requested session)")
            self.add(sid, f"Switch to {sd.name}", "positive", sc,
                     f"ECU accepts session {sd.name} and reports P2/P2* timing.",
                     [k_sub(sid, sub)], [f"session:0x{sub:02X}"])
        self._unsupported_sub_case(sid, lambda s: _b(sid, s))
        self._length_cases(sid, [(_b(sid), "Request without sub-function"),
                                 (_b(sid, 0x03, 0x00), "Request with one extra byte")],
                           session=self._pick(svc.sessions))
        # suppressPositiveResponse
        sc = self.sc()
        sc.send(_b(sid, 0x83), "Extended session with suppressPositiveResponse bit set")
        self._read_session_did(sc, "(session must have changed although no reply was sent)")
        self.add(sid, "Suppress positive response on session control", "positive", sc,
                 "With bit 7 of the sub-function set the ECU performs the action but sends no positive response.",
                 [k_misc(sid, "spr")], ["feature:spr"])
        # security re-lock on session change
        prot = next((d for d in self.p.writable_dids if d.write.security is not None), None)
        if prot and 0x27 in self.p.services:
            level = prot.write.security
            sess = self._secure_session(prot.write.sessions, 0x2E, level)
            if sess:
                sc = self.sc()
                sc.enter(sess)
                sc.unlock(level)
                sc.send(_b(sid, sess), f"Re-enter {self.p.session_name(sess)} (session change)")
                sc.send(_b(0x2E) + _did_bytes(prot.id) + prot.example_bytes(),
                        f"Write {prot.name}: security must be locked again")
                self.add(sid, "Security is re-locked after a session change", "security", sc,
                         "A successful DiagnosticSessionControl request re-locks security access.",
                         [k_misc(sid, "relock"), k_nrc(0x2E, 0x33)], [f"did:0x{prot.id:04X}", "feature:relock"])

    # -- 0x11 ---------------------------------------------------------------------------------
    def gen_11(self) -> None:
        sid = 0x11
        if sid not in self.p.services:
            return
        svc = self.p.services[sid]
        sess = self._pick(svc.sessions)
        for sub, sd in svc.subfunctions.items():
            sc = self.sc()
            sc.enter(sess)
            sc.send(_b(sid, sub), f"Request {sd.name}")
            self._read_session_did(sc, "(ECU must be back in default session)")
            self.add(sid, f"ECU reset: {sd.name}", "positive", sc,
                     "ECU accepts the reset and returns to the default session.",
                     [k_sub(sid, sub)], [])
        self._unsupported_sub_case(sid, lambda s: _b(sid, s))
        first = next(iter(svc.subfunctions))
        self._length_cases(sid, [(_b(sid), "Request without sub-function"),
                                 (_b(sid, first, 0x00), "Request with one extra byte")], session=sess)
        self._wrong_session_case(sid, _b(sid, first), "Request ECU reset")

    # -- 0x14 ---------------------------------------------------------------------------------
    def gen_14(self) -> None:
        sid = 0x14
        if sid not in self.p.services:
            return
        can_read = 0x19 in self.p.services and 0x01 in self.p.services[0x19].subfunctions
        sess = self._pick(self._svc_sessions(sid))
        sc = self.sc()
        sc.enter(sess)
        if can_read:
            sc.send(_b(0x19, 0x01, 0xFF), "Count DTCs before clearing")
        sc.send(_b(sid, 0xFF, 0xFF, 0xFF), "Clear all DTCs")
        if can_read:
            sc.send(_b(0x19, 0x01, 0xFF), "Count DTCs after clearing (must be 0)")
        self.add(sid, "Clear all DTCs", "positive", sc, "Group FFFFFF clears every stored DTC.",
                 [], [])
        if self.p.dtcs:
            code = self.p.dtcs[0].code
            sc = self.sc()
            sc.enter(sess)
            sc.send(_b(sid) + code.to_bytes(3, "big"), f"Clear single DTC 0x{code:06X}")
            if 0x19 in self.p.services and 0x0A in self.p.services[0x19].subfunctions:
                sc.send(_b(0x19, 0x0A), "List DTCs (cleared one must be gone)")
            self.add(sid, "Clear a single DTC group", "positive", sc, "A specific DTC can be cleared on its own.",
                     [], [])
        sc = self.sc()
        sc.enter(sess)
        used = {d.code for d in self.p.dtcs}
        bad = next(c for c in (0x123456, 0x654321, 0xABCDEF) if c not in used)
        sc.send(_b(sid) + bad.to_bytes(3, "big"), f"Clear unsupported group 0x{bad:06X}")
        self.add(sid, "Clear unsupported DTC group is rejected", "negative", sc,
                 "Unknown DTC groups must be rejected with NRC 0x31.", [k_nrc(sid, 0x31)], [])
        self._length_cases(sid, [(_b(sid, 0xFF, 0xFF), "Group of DTC too short"),
                                 (_b(sid, 0xFF, 0xFF, 0xFF, 0x00), "Group of DTC too long")], session=sess)
        self._wrong_session_case(sid, _b(sid, 0xFF, 0xFF, 0xFF), "Clear DTCs")

    # -- 0x19 ---------------------------------------------------------------------------------
    def gen_19(self) -> None:
        sid = 0x19
        if sid not in self.p.services:
            return
        svc = self.p.services[sid]
        sess = self._pick(svc.sessions)
        for sub, sd in svc.subfunctions.items():
            sc = self.sc()
            sc.enter(sess)
            req = _b(sid, sub) if sub == 0x0A else _b(sid, sub, 0xFF)
            sc.send(req, f"Request {sd.name}")
            if sub == 0x02 and self.p.dtcs:
                mask = self.p.dtcs[1 % len(self.p.dtcs)].status & -self.p.dtcs[1 % len(self.p.dtcs)].status
                sc.send(_b(sid, sub, mask), f"Request {sd.name} filtered with mask 0x{mask:02X}")
            self.add(sid, f"Read DTC information: {sd.name}", "positive", sc,
                     "ECU reports the DTCs that match the request.", [k_sub(sid, sub)], [])
        self._unsupported_sub_case(sid, lambda s: _b(sid, s, 0xFF))
        bad = [(_b(sid), "Request without sub-function")]
        if 0x01 in svc.subfunctions:
            bad.append((_b(sid, 0x01), "reportNumberOfDTCByStatusMask without status mask"))
        if 0x0A in svc.subfunctions:
            bad.append((_b(sid, 0x0A, 0x00), "reportSupportedDTC with one extra byte"))
        self._length_cases(sid, bad, session=sess)
        self._wrong_session_case(sid, _b(sid, 0x0A), "Read DTC information")

    # -- 0x22 ---------------------------------------------------------------------------------
    def gen_22(self) -> None:
        sid = 0x22
        if sid not in self.p.services:
            return
        for d in self.p.readable_dids:
            lvl = d.read.security
            sess = self._secure_session(d.read.sessions, sid, lvl)
            tg = [f"did:0x{d.id:04X}", f"name:{d.name.lower()}"]
            if sess is not None:
                sc = self.sc()
                sc.enter(sess)
                if lvl is not None:
                    sc.unlock(lvl)
                sc.send(_b(sid) + _did_bytes(d.id), f"Read {d.name} (DID 0x{d.id:04X})")
                self.add(sid, f"Read {d.name}", "positive", sc,
                         f"DID 0x{d.id:04X} is readable in {self.p.session_name(sess)}"
                         + (f" after unlocking level {lvl}." if lvl else "."),
                         [k_did(sid, d.id, "pos")], tg)
            if lvl is not None:
                sess_ns = self._pick([s for s in d.read.sessions if s in self._svc_sessions(sid)])
                sc = self.sc()
                sc.enter(sess_ns)
                sc.send(_b(sid) + _did_bytes(d.id), f"Read {d.name} while locked")
                self.add(sid, f"Read {d.name} without security access", "security", sc,
                         f"DID 0x{d.id:04X} requires security level {lvl}.",
                         [k_did(sid, d.id, "sec_denied"), k_nrc(sid, 0x33)], tg)
            wrong = [s for s in self._svc_sessions(sid) if s not in d.read.sessions]
            if wrong:
                sc = self.sc()
                sc.enter(wrong[0])
                sc.send(_b(sid) + _did_bytes(d.id), f"Read {d.name} in {self.p.session_name(wrong[0])}")
                self.add(sid, f"Read {d.name} in unsupported session", "session", sc,
                         f"DID 0x{d.id:04X} is not available in {self.p.session_name(wrong[0])}.",
                         [k_did(sid, d.id, "wrong_session"), k_nrc(sid, 0x31)], tg)
        sess = self._pick(self._svc_sessions(sid))
        sc = self.sc()
        sc.enter(sess)
        unused = next(x for x in (UNUSED_DID, 0xBEEE, 0xBEED) if self.p.did(x) is None)
        sc.send(_b(sid) + _did_bytes(unused), f"Read unsupported DID 0x{unused:04X}")
        self.add(sid, "Read unsupported DID", "negative", sc, "Unknown DIDs must be rejected with NRC 0x31.",
                 [k_nrc(sid, 0x31)], [])
        open_dids = [d for d in self.p.readable_dids if 0x01 in d.read.sessions and d.read.security is None]
        if len(open_dids) >= 2:
            a, b = open_dids[0], open_dids[1]
            sc = self.sc()
            sc.send(_b(sid) + _did_bytes(a.id) + _did_bytes(b.id), f"Read {a.name} and {b.name} in one request")
            self.add(sid, "Read multiple DIDs in one request", "positive", sc,
                     "The response contains every requested DID record in request order.",
                     [k_misc(sid, "multi")], [f"did:0x{a.id:04X}", f"did:0x{b.id:04X}"])
        any_did = self.p.readable_dids[0]
        self._length_cases(sid, [(_b(sid), "Request without a DID"),
                                 (_b(sid, any_did.id >> 8), "Request with half a DID"),
                                 (_b(sid) + _did_bytes(any_did.id) + _b(0x01), "Request with trailing byte")],
                           session=sess)
        self._wrong_session_case(sid, _b(sid) + _did_bytes(any_did.id), "Read DID")

    # -- 0x27 ---------------------------------------------------------------------------------
    def gen_27(self) -> None:
        sid = 0x27
        if sid not in self.p.services or not self.p.security_levels:
            return
        sess = self._pick(self._svc_sessions(sid))
        for i, lvl in enumerate(self.p.security_levels):
            n = lvl.seed_length
            sc = self.sc()
            sc.enter(sess)
            sc.send(_b(sid, lvl.level), f"Request seed (level {lvl.level})")
            self.add(sid, f"Request seed for level {lvl.level}", "positive", sc,
                     f"ECU returns a {n}-byte non-zero seed.", [k_sub(sid, lvl.level)],
                     [f"level:{lvl.level}"])
            sc = self.sc()
            sc.enter(sess)
            sc.unlock(lvl.level, role="test")
            sc.send(_b(sid, lvl.level), "Request seed again while unlocked (expect all-zero seed)")
            self.add(sid, f"Unlock level {lvl.level} with valid key", "security", sc,
                     "A valid key unlocks the level; re-requesting a seed then returns zeros.",
                     [k_sub(sid, lvl.send_key_sub), k_misc(sid, "already_unlocked")], [f"level:{lvl.level}"])
            sc = self.sc()
            sc.enter(sess)
            sc.send(_b(sid, lvl.level), f"Request seed (level {lvl.level})")
            sc.send(_b(sid, lvl.send_key_sub) + bytes(lvl.key_length), "Send invalid key", key="bad", level=lvl.level)
            self.add(sid, f"Invalid key is rejected (level {lvl.level})", "security", sc,
                     "An incorrect key is answered with NRC 0x35 and leaves the ECU locked.",
                     [k_nrc(sid, 0x35)], [f"level:{lvl.level}"])
            if i > 0:
                continue
            sc = self.sc()
            sc.enter(sess)
            sc.send(_b(sid, lvl.send_key_sub) + bytes(lvl.key_length), "Send key without requesting a seed",
                    key="good", level=lvl.level)
            self.add(sid, "Send key without seed is a sequence error", "security", sc,
                     "sendKey before requestSeed must be rejected with NRC 0x24.", [k_nrc(sid, 0x24)],
                     [f"level:{lvl.level}"])
            # attempt limit + lock-out
            sc = self.sc()
            sc.enter(sess)
            for a in range(lvl.max_attempts):
                sc.send(_b(sid, lvl.level), f"Request seed (attempt {a + 1})")
                sc.send(_b(sid, lvl.send_key_sub) + bytes(lvl.key_length), f"Send invalid key (attempt {a + 1})",
                        key="bad", level=lvl.level)
            sc.send(_b(sid, lvl.level), "Request seed during lock-out delay")
            self.add(sid, "Attempt limit and lock-out delay", "security", sc,
                     f"After {lvl.max_attempts} invalid keys the ECU answers 0x36 and then 0x37 for "
                     f"{lvl.lockout_ms} ms.", [k_nrc(sid, 0x36), k_nrc(sid, 0x37)], [f"level:{lvl.level}"])
            sc = self.sc()
            sc.enter(sess)
            for a in range(lvl.max_attempts):
                sc.send(_b(sid, lvl.level), f"Request seed (attempt {a + 1})")
                sc.send(_b(sid, lvl.send_key_sub) + bytes(lvl.key_length), f"Send invalid key (attempt {a + 1})",
                        key="bad", level=lvl.level)
            sc.alive_wait(lvl.lockout_ms + 100, "Wait for the lock-out delay to expire")
            sc.enter(sess)
            sc.send(_b(sid, lvl.level), "Request seed after lock-out delay")
            self.add(sid, "Lock-out delay expires", "timing", sc,
                     "After the delay a seed can be requested again.", [k_misc(sid, "lockout_expiry")],
                     [f"level:{lvl.level}", "feature:timing"])
            first = lvl
            self._length_cases(sid, [(_b(sid), "Request without sub-function"),
                                     (_b(sid, first.level, 0x00), "requestSeed with extra byte")],
                               session=sess, title="requestSeed incorrect length")
            sc = self.sc()
            sc.enter(sess)
            sc.send(_b(sid, first.level), "Request seed")
            sc.send(_b(sid, first.send_key_sub) + bytes(max(first.key_length - 1, 0)), "Send key that is one byte short")
            self.add(sid, "sendKey with incorrect length", "negative", sc,
                     "A key of the wrong length is rejected with NRC 0x13.", [k_nrc(sid, 0x13)], [])
            self._unsupported_sub_case(sid, lambda s: _b(sid, s))
        self._wrong_session_case(sid, _b(sid, self.p.security_levels[0].level), "Request seed")

    # -- 0x28 ---------------------------------------------------------------------------------
    def gen_28(self) -> None:
        sid = 0x28
        if sid not in self.p.services:
            return
        svc = self.p.services[sid]
        sess = self._pick(svc.sessions)
        first = next(iter(svc.subfunctions))
        for sub, sd in svc.subfunctions.items():
            sc = self.sc()
            sc.enter(sess)
            sc.send(_b(sid, sub, 0x01), f"{sd.name} for normal messages")
            if sub != 0x00 and 0x00 in svc.subfunctions:
                sc.send(_b(sid, 0x00, 0x01), "Restore communication", role="cleanup")
            self.add(sid, f"Communication control: {sd.name}", "positive", sc,
                     "ECU accepts the control type for normal communication messages.", [k_sub(sid, sub)], [])
        sc = self.sc()
        sc.enter(sess)
        sc.send(_b(sid, first, 0x00), "communicationType 0x00 (invalid)")
        sc.send(_b(sid, first, 0x04), "communicationType 0x04 (invalid)")
        self.add(sid, "Invalid communicationType", "negative", sc,
                 "Undefined communication types must be rejected with NRC 0x31.", [k_nrc(sid, 0x31)], [])
        self._unsupported_sub_case(sid, lambda s: _b(sid, s, 0x01))
        self._length_cases(sid, [(_b(sid, first), "Missing communicationType"),
                                 (_b(sid, first, 0x01, 0x00), "Extra byte")], session=sess)
        self._wrong_session_case(sid, _b(sid, first, 0x01), "Communication control")

    # -- 0x2E ---------------------------------------------------------------------------------
    def gen_2E(self) -> None:
        sid = 0x2E
        if sid not in self.p.services:
            return
        for d in self.p.writable_dids:
            w = d.write
            lvl = w.security
            sess = self._secure_session(w.sessions, sid, lvl)
            tg = [f"did:0x{d.id:04X}", f"name:{d.name.lower()}"]
            req = lambda data: _b(sid) + _did_bytes(d.id) + data  # noqa: E731
            if sess is not None:
                sc = self.sc()
                sc.enter(sess)
                if lvl is not None:
                    sc.unlock(lvl)
                readable = d.read and sess in d.read.sessions
                if readable and d.read.security is not None and d.read.security != lvl:
                    sc.unlock(d.read.security)
                sc.send(req(d.example_bytes()), f"Write {d.name}")
                if readable:
                    sc.send(_b(0x22) + _did_bytes(d.id), f"Read back {d.name} (must equal the written value)")
                self.add(sid, f"Write {d.name}", "positive", sc,
                         f"DID 0x{d.id:04X} accepts a valid value and the value persists.",
                         [k_did(sid, d.id, "pos")], tg)
                # bad length
                sc = self.sc()
                sc.enter(sess)
                sc.send(req(bytes(max(d.length - 1, 0))), f"Write {d.name} with {d.length - 1} data byte(s)")
                sc.send(req(bytes(d.length + 1)), f"Write {d.name} with {d.length + 1} data byte(s)")
                self.add(sid, f"Write {d.name} with wrong data length", "negative", sc,
                         f"Data length must equal {d.length}.", [k_did(sid, d.id, "bad_length"), k_nrc(sid, 0x13)], tg)
                # invalid values
                bad = _invalid_values(d)
                if bad:
                    sc = self.sc()
                    sc.enter(sess)
                    if lvl is not None:
                        sc.unlock(lvl)
                    for v in bad:
                        sc.send(req(v), f"Write {d.name} with invalid value {v.hex().upper()}")
                    self.add(sid, f"Write {d.name} with out-of-range value", "negative", sc,
                             "Invalid values must be rejected with NRC 0x31.",
                             [k_did(sid, d.id, "invalid_value"), k_nrc(sid, 0x31)], tg)
                # boundary values
                if d.data_type == "uint" and d.min is not None and d.max is not None:
                    sc = self.sc()
                    sc.enter(sess)
                    if lvl is not None:
                        sc.unlock(lvl)
                    for v in (d.min, d.max):
                        sc.send(req(v.to_bytes(d.length, "big")), f"Write boundary value {v}")
                    self.add(sid, f"Write {d.name} boundary values", "boundary", sc,
                             f"Minimum ({d.min}) and maximum ({d.max}) are accepted.", [], tg)
                # security denied
                if lvl is not None:
                    sc = self.sc()
                    sc.enter(sess)
                    sc.send(req(d.example_bytes()), f"Write {d.name} while locked")
                    self.add(sid, f"Write {d.name} without security access", "security", sc,
                             f"Writing needs security level {lvl}.",
                             [k_did(sid, d.id, "sec_denied"), k_nrc(sid, 0x33)], tg)
            wrong = [s for s in self._svc_sessions(sid) if s not in w.sessions]
            if wrong:
                sc = self.sc()
                sc.enter(wrong[0])
                sc.send(req(d.example_bytes()), f"Write {d.name} in {self.p.session_name(wrong[0])}")
                self.add(sid, f"Write {d.name} in unsupported session", "session", sc,
                         f"DID 0x{d.id:04X} is not writable in {self.p.session_name(wrong[0])}.",
                         [k_did(sid, d.id, "wrong_session"), k_nrc(sid, 0x31)], tg)
        sess = self._pick(self._svc_sessions(sid))
        sc = self.sc()
        sc.enter(sess)
        ro = next((d for d in self.p.readable_dids if d.write is None), None)
        if ro:
            sc.send(_b(sid) + _did_bytes(ro.id) + bytes(ro.length), f"Write read-only DID {ro.name}")
        unused = next(x for x in (UNUSED_DID, 0xBEEE, 0xBEED) if self.p.did(x) is None)
        sc.send(_b(sid) + _did_bytes(unused) + b"\x00", f"Write unsupported DID 0x{unused:04X}")
        self.add(sid, "Write read-only or unsupported DID", "negative", sc,
                 "DIDs that are not writable must be rejected with NRC 0x31.", [k_nrc(sid, 0x31)], [])
        self._length_cases(sid, [(_b(sid), "Request without DID"), (_b(sid, 0xF1), "Request with half a DID")],
                           session=sess)
        w0 = self.p.writable_dids[0]
        self._wrong_session_case(sid, _b(sid) + _did_bytes(w0.id) + w0.example_bytes(), "Write DID")

    # -- 0x31 ---------------------------------------------------------------------------------
    def gen_31(self) -> None:
        sid = 0x31
        if sid not in self.p.services:
            return
        svc = self.p.services[sid]
        for r in self.p.routines:
            lvl = r.security
            sess = self._secure_session(r.sessions, sid, lvl)
            tg = [f"rid:0x{r.id:04X}", f"name:{r.name.lower()}"]
            rid = _did_bytes(r.id)
            opt = bytes(r.option_length)
            if sess is None:
                continue

            def prep(sc: Scenario) -> None:
                sc.enter(sess)
                if lvl is not None:
                    sc.unlock(lvl)

            sc = self.sc()
            prep(sc)
            sc.send(_b(sid, 0x01) + rid + opt, f"Start routine {r.name}")
            sc.send(_b(sid, 0x03) + rid, f"Request results of {r.name}")
            sc.send(_b(sid, 0x02) + rid, f"Stop routine {r.name}")
            self.add(sid, f"Run routine {r.name}", "positive", sc,
                     f"Routine 0x{r.id:04X} can be started, queried and stopped.",
                     [k_rid(r.id, "pos")] + [k_sub(sid, s) for s in (1, 2, 3)], tg)
            sc = self.sc()
            prep(sc)
            sc.send(_b(sid, 0x02) + rid, f"Stop {r.name} before it was started")
            sc.send(_b(sid, 0x03) + rid, f"Request results of {r.name} before it was started")
            self.add(sid, f"Routine {r.name}: sequence errors", "negative", sc,
                     "Stop / results without a preceding start must be rejected with NRC 0x24.",
                     [k_rid(r.id, "seq_error"), k_nrc(sid, 0x24)], tg)
            if r.single_instance:
                sc = self.sc()
                prep(sc)
                sc.send(_b(sid, 0x01) + rid + opt, f"Start routine {r.name}")
                sc.send(_b(sid, 0x01) + rid + opt, f"Start routine {r.name} again while running")
                self.add(sid, f"Routine {r.name}: second start while running", "negative", sc,
                         "A running single-instance routine must not be started twice (NRC 0x22).",
                         [k_nrc(sid, 0x22)], tg)
            sc = self.sc()
            sc.enter(sess)
            sc.send(_b(sid, 0x01) + rid + opt + b"\x00", f"Start {r.name} with {r.option_length + 1} option byte(s)")
            if r.option_length > 0:
                sc.send(_b(sid, 0x01) + rid + bytes(r.option_length - 1),
                        f"Start {r.name} with {r.option_length - 1} option byte(s)")
            self.add(sid, f"Routine {r.name}: wrong option length", "negative", sc,
                     f"Start expects {r.option_length} option byte(s).",
                     [k_rid(r.id, "bad_length"), k_nrc(sid, 0x13)], tg)
            if lvl is not None:
                sc = self.sc()
                sc.enter(sess)
                sc.send(_b(sid, 0x01) + rid + opt, f"Start {r.name} while locked")
                self.add(sid, f"Routine {r.name}: security denied", "security", sc,
                         f"Routine needs security level {lvl}.", [k_rid(r.id, "sec_denied"), k_nrc(sid, 0x33)], tg)
            wrong = [s for s in svc.sessions if s not in r.sessions]
            if wrong:
                sc = self.sc()
                sc.enter(wrong[0])
                sc.send(_b(sid, 0x01) + rid + opt, f"Start {r.name} in {self.p.session_name(wrong[0])}")
                self.add(sid, f"Routine {r.name} in unsupported session", "session", sc,
                         f"RID 0x{r.id:04X} is not available in {self.p.session_name(wrong[0])}.",
                         [k_rid(r.id, "wrong_session"), k_nrc(sid, 0x31)], tg)
        sess = self._pick(svc.sessions)
        sc = self.sc()
        sc.enter(sess)
        unused = next(x for x in (UNUSED_RID, 0xBEEE, 0xBEED) if self.p.routine(x) is None)
        sc.send(_b(sid, 0x01) + _did_bytes(unused), f"Start unsupported RID 0x{unused:04X}")
        self.add(sid, "Unsupported routine identifier", "negative", sc,
                 "Unknown RIDs must be rejected with NRC 0x31.", [k_nrc(sid, 0x31)], [])
        r0 = self.p.routines[0] if self.p.routines else None
        if r0:
            self._unsupported_sub_case(sid, lambda s: _b(sid, s) + _did_bytes(r0.id))
            self._length_cases(sid, [(_b(sid), "Request without sub-function"),
                                     (_b(sid, 0x01), "Request without RID")], session=sess)
            self._wrong_session_case(sid, _b(sid, 0x01) + _did_bytes(r0.id) + bytes(r0.option_length), "Start routine")

    # -- 0x3E ---------------------------------------------------------------------------------
    def gen_3E(self) -> None:
        sid = 0x3E
        if sid not in self.p.services:
            return
        sc = self.sc()
        sc.send(_b(sid, 0x00), "TesterPresent")
        self.add(sid, "TesterPresent", "positive", sc, "ECU answers 7E 00.", [k_sub(sid, 0)], [])
        sc = self.sc()
        sc.send(_b(sid, 0x80), "TesterPresent with suppressPositiveResponse bit")
        self.add(sid, "TesterPresent with suppressed response", "positive", sc,
                 "No response is expected when bit 7 is set.", [k_misc(sid, "spr")], ["feature:spr"])
        self._unsupported_sub_case(sid, lambda s: _b(sid, s))
        self._length_cases(sid, [(_b(sid), "Request without sub-function"), (_b(sid, 0x00, 0x00), "Extra byte")],
                           session=0x01)
        s3 = self.p.timing.s3_ms
        ext = 0x03 if 0x03 in self.p.sessions else None
        if self.session_did and ext and 0x10 in self.p.services:
            sc = self.sc()
            sc.enter(ext)
            sc.wait(s3 + 200, f"Stay silent longer than S3 ({s3} ms)")
            self._read_session_did(sc, "(ECU must have fallen back to default session)")
            self.add(sid, "S3 timeout returns ECU to default session", "timing", sc,
                     f"Without requests for more than {s3} ms a non-default session ends.",
                     [k_misc(sid, "s3_timeout")], ["feature:timing"])
            sc = self.sc()
            sc.enter(ext)
            for i in range(3):
                sc.wait(s3 - 1000, f"Wait {s3 - 1000} ms (below S3)")
                sc.send(_b(sid, 0x00), f"TesterPresent {i + 1}/3")
            self._read_session_did(sc, "(session must still be extended after > S3 in total)")
            self.add(sid, "TesterPresent keeps the session alive", "timing", sc,
                     "Periodic TesterPresent prevents the S3 timeout.", [k_misc(sid, "keepalive")],
                     ["feature:timing"])

    # -- 0x85 ---------------------------------------------------------------------------------
    def gen_85(self) -> None:
        sid = 0x85
        if sid not in self.p.services:
            return
        svc = self.p.services[sid]
        sess = self._pick(svc.sessions)
        for sub, sd in svc.subfunctions.items():
            sc = self.sc()
            sc.enter(sess)
            sc.send(_b(sid, sub), f"Control DTC setting: {sd.name}")
            if sub != 0x01 and 0x01 in svc.subfunctions:
                sc.send(_b(sid, 0x01), "Switch DTC setting back on", role="cleanup")
            self.add(sid, f"Control DTC setting {sd.name}", "positive", sc,
                     "ECU accepts the DTC setting change.", [k_sub(sid, sub)], [])
        self._unsupported_sub_case(sid, lambda s: _b(sid, s))
        first = next(iter(svc.subfunctions))
        self._length_cases(sid, [(_b(sid), "Request without sub-function"), (_b(sid, first, 0x00), "Extra byte")],
                           session=sess)
        self._wrong_session_case(sid, _b(sid, first), "Control DTC setting")


def build_suite(profile: ECUProfile) -> list[TestCase]:
    return SuiteBuilder(profile).build()
