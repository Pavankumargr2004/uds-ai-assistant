"""A software UDS server (mock ECU) driven by an ECU profile.

It exists so the whole pipeline (generate -> review -> execute -> report) can be
demonstrated and regression-tested without hardware. It is written in classic
"ECU handler" style (raise an NRC, otherwise return the response) and is
deliberately independent of ``protocol.oracle`` so that running oracle-generated
tests against it is a genuine cross-check.

Fault injection lets you prove that the generated tests really detect defects.
"""
from __future__ import annotations

import random
from typing import Iterable, Optional

from ..protocol.catalog import SERVICES
from ..protocol.profile import ECUProfile

FAULTS: dict[str, str] = {
    "wrong_nrc_bad_length_22": "ReadDataByIdentifier answers 0x31 instead of 0x13 for a malformed length",
    "skip_write_security": "WriteDataByIdentifier does not enforce the security level",
    "no_relock_on_session_change": "Security stays unlocked after a session change",
    "s3_not_enforced": "S3 timeout never returns the ECU to the default session",
    "accept_any_key": "SecurityAccess accepts any key",
    "no_attempt_limit": "SecurityAccess never locks out after repeated invalid keys",
    "ignore_spr": "suppressPositiveResponse bit is ignored (ECU replies anyway)",
    "write_not_persisted": "WriteDataByIdentifier answers positively but does not store the value",
}


class _NRC(Exception):
    def __init__(self, code: int):
        super().__init__(code)
        self.code = code


class MockECU:
    def __init__(self, profile: ECUProfile, faults: Iterable[str] = (), seed: int = 2026):
        unknown = set(faults) - set(FAULTS)
        if unknown:
            raise ValueError(f"unknown fault(s): {sorted(unknown)}")
        self.p = profile
        self.faults = set(faults)
        self._seed = seed
        self.reset()

    # -- lifecycle -----------------------------------------------------------------------------
    def reset(self) -> None:
        """Power-on state."""
        self._rng = random.Random(self._seed)
        self.now_ms = 0
        self._last_rx = 0
        self.session = 0x01
        self.unlocked: set[int] = set()
        self._seed_for: dict[int, bytes] = {}
        self._bad_attempts: dict[int, int] = {}
        self._locked_until: dict[int, int] = {}
        self.data = {d.id: bytearray(d.default_bytes()) for d in self.p.dids}
        self.dtcs: dict[int, int] = {d.code: d.status for d in self.p.dtcs}
        self.routine_state: dict[int, str] = {}
        self.comm_state = 0x00
        self.dtc_setting_on = True
        self.log: list[tuple[int, bytes, list[bytes]]] = []

    def advance(self, ms: int) -> None:
        self.now_ms += ms
        self._s3_check()

    def _s3_check(self) -> None:
        if "s3_not_enforced" in self.faults:
            return
        if self.session != 0x01 and self.now_ms - self._last_rx > self.p.timing.s3_ms:
            self.session = 0x01
            self.unlocked.clear()
            self._seed_for.clear()

    # -- transport-level entry point -----------------------------------------------------------
    def process(self, req: bytes) -> list[bytes]:
        """Handle one request; return all frames sent (pending NRC 0x78 frames, then the final one)."""
        self._s3_check()
        self._last_rx = self.now_ms
        frames: list[bytes] = []
        try:
            resp = self._handle(req)
            if resp is not None:
                sid = req[0]
                if sid == 0x31 and len(req) >= 4 and req[1] & 0x7F == 1:
                    r = self.p.routine(int.from_bytes(req[2:4], "big"))
                    if r and r.send_pending:
                        frames.append(bytes([0x7F, sid, 0x78]))
                frames.append(resp)
        except _NRC as e:
            frames.append(bytes([0x7F, req[0], e.code]))
        self.log.append((self.now_ms, req, frames))
        return frames

    # -- dispatch ------------------------------------------------------------------------------
    def _handle(self, req: bytes) -> Optional[bytes]:
        sid = req[0]
        svc = self.p.services.get(sid)
        if svc is None:
            raise _NRC(0x11)
        if self.session not in svc.sessions:
            raise _NRC(0x7F)
        sub = None
        spr = False
        if SERVICES[sid].has_subfunction:
            if len(req) < 2:
                raise _NRC(0x13)
            sub, spr = req[1] & 0x7F, bool(req[1] & 0x80)
            if sub not in svc.subfunctions:
                raise _NRC(0x12)
            sd = svc.subfunctions[sub]
            if sd.sessions is not None and self.session not in sd.sessions:
                raise _NRC(0x7E)
        resp = getattr(self, f"_h_{sid:02X}")(req, sub)
        if spr and "ignore_spr" not in self.faults:
            return None
        return resp

    def _need_len(self, req: bytes, n: int) -> None:
        if len(req) != n:
            raise _NRC(0x13)

    def _is_unlocked(self, level: Optional[int]) -> bool:
        return level is None or level in self.unlocked

    # -- services ------------------------------------------------------------------------------
    def _h_10(self, req, sub):
        self._need_len(req, 2)
        self.session = sub
        if "no_relock_on_session_change" not in self.faults:
            self.unlocked.clear()
        self._seed_for.clear()
        t = self.p.timing
        return bytes([0x50, sub]) + t.p2_ms.to_bytes(2, "big") + (t.p2_star_ms // 10).to_bytes(2, "big")

    def _h_11(self, req, sub):
        self._need_len(req, 2)
        self.session = 0x01
        self.unlocked.clear()
        self._seed_for.clear()
        self.routine_state.clear()
        self.comm_state = 0x00
        return bytes([0x51, sub])

    def _h_14(self, req, sub):
        self._need_len(req, 4)
        group = int.from_bytes(req[1:4], "big")
        if group == 0xFFFFFF:
            self.dtcs.clear()
        elif group in {d.code for d in self.p.dtcs}:
            self.dtcs.pop(group, None)
        else:
            raise _NRC(0x31)
        return bytes([0x54])

    def _h_19(self, req, sub):
        self._need_len(req, 2 if sub == 0x0A else 3)
        if sub == 0x0A:
            rows = list(self.dtcs.items())
        else:
            rows = [(c, s) for c, s in self.dtcs.items() if s & req[2]]
        if sub == 0x01:
            return bytes([0x59, 0x01, 0xFF, 0x01]) + len(rows).to_bytes(2, "big")
        out = bytes([0x59, sub, 0xFF])
        for code, status in rows:
            out += code.to_bytes(3, "big") + bytes([status])
        return out

    def _h_22(self, req, sub):
        body = req[1:]
        if len(body) < 2 or len(body) % 2:
            raise _NRC(0x31 if "wrong_nrc_bad_length_22" in self.faults else 0x13)
        dids = []
        for i in range(0, len(body), 2):
            d = self.p.did(int.from_bytes(body[i:i + 2], "big"))
            if d is None or d.read is None or self.session not in d.read.sessions:
                raise _NRC(0x31)
            dids.append(d)
        for d in dids:
            if not self._is_unlocked(d.read.security):
                raise _NRC(0x33)
        out = bytes([0x62])
        for d in dids:
            val = bytes([self.session]) if d.live == "active_session" else bytes(self.data[d.id])
            out += d.id.to_bytes(2, "big") + val
        return out

    def _h_27(self, req, sub):
        lvl, kind = self.p.security_by_sub(sub)
        if lvl is None:
            raise _NRC(0x12)
        if kind == "seed":
            self._need_len(req, 2)
            if self._locked_until.get(lvl.level, 0) > self.now_ms:
                raise _NRC(0x37)
            if lvl.level in self._locked_until:
                del self._locked_until[lvl.level]
                self._bad_attempts[lvl.level] = 0
            if lvl.level in self.unlocked:
                return bytes([0x67, sub]) + bytes(lvl.seed_length)
            seed = bytes(self._rng.randrange(1, 256) for _ in range(lvl.seed_length))
            self._seed_for[lvl.level] = seed
            return bytes([0x67, sub]) + seed
        self._need_len(req, 2 + lvl.key_length)
        seed = self._seed_for.pop(lvl.level, None)
        if seed is None:
            raise _NRC(0x24)
        if "accept_any_key" in self.faults or req[2:] == lvl.compute_key(seed):
            self.unlocked.add(lvl.level)
            self._bad_attempts[lvl.level] = 0
            return bytes([0x67, sub])
        self._bad_attempts[lvl.level] = self._bad_attempts.get(lvl.level, 0) + 1
        if self._bad_attempts[lvl.level] >= lvl.max_attempts and "no_attempt_limit" not in self.faults:
            self._locked_until[lvl.level] = self.now_ms + lvl.lockout_ms
            raise _NRC(0x36)
        raise _NRC(0x35)

    def _h_28(self, req, sub):
        self._need_len(req, 3)
        if req[2] not in (1, 2, 3):
            raise _NRC(0x31)
        self.comm_state = sub
        return bytes([0x68, sub])

    def _h_2E(self, req, sub):
        if len(req) < 3:
            raise _NRC(0x13)
        d = self.p.did(int.from_bytes(req[1:3], "big"))
        if d is None or d.write is None or self.session not in d.write.sessions:
            raise _NRC(0x31)
        self._need_len(req, 3 + d.length)
        if "skip_write_security" not in self.faults and not self._is_unlocked(d.write.security):
            raise _NRC(0x33)
        if d.value_error(req[3:]):
            raise _NRC(0x31)
        if "write_not_persisted" not in self.faults:
            self.data[d.id] = bytearray(req[3:])
        return bytes([0x6E]) + req[1:3]

    def _h_31(self, req, sub):
        if len(req) < 4:
            raise _NRC(0x13)
        rid = int.from_bytes(req[2:4], "big")
        r = self.p.routine(rid)
        if r is None or self.session not in r.sessions:
            raise _NRC(0x31)
        if sub not in r.subfunctions:
            raise _NRC(0x12)
        self._need_len(req, 4 + (r.option_length if sub == 1 else 0))
        if not self._is_unlocked(r.security):
            raise _NRC(0x33)
        state = self.routine_state.get(rid)
        if sub == 1:
            if r.single_instance and state == "running":
                raise _NRC(0x22)
            self.routine_state[rid] = "running"
        elif sub == 2:
            if state != "running":
                raise _NRC(0x24)
            self.routine_state[rid] = "stopped"
        elif state is None:
            raise _NRC(0x24)
        return bytes([0x71, sub]) + req[2:4] + r.resp_bytes(sub)

    def _h_3E(self, req, sub):
        self._need_len(req, 2)
        return bytes([0x7E, 0x00])

    def _h_85(self, req, sub):
        self._need_len(req, 2)
        self.dtc_setting_on = sub == 0x01
        return bytes([0xC5, sub])
