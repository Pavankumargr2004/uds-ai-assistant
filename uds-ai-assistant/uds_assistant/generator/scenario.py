"""Scenario builder: writes test steps while the oracle tracks protocol state."""
from __future__ import annotations

from typing import Optional

from ..protocol.hexutil import to_hex
from ..protocol.oracle import Expectation, SpecOracle, State
from ..protocol.profile import ECUProfile
from .models import Step


class Scenario:
    def __init__(self, oracle: SpecOracle):
        self.o = oracle
        self.p: ECUProfile = oracle.p
        self.state: State = oracle.initial_state()
        self.steps: list[Step] = []

    # -- primitives ---------------------------------------------------------------------------
    def peek(self, req: bytes, key_valid: bool = True) -> Expectation:
        exp, _ = self.o.step(req, self.state, key_valid)
        return exp

    def send(self, req: bytes, desc: str, role: str = "test", *, key: Optional[str] = None,
             level: Optional[int] = None) -> Expectation:
        """Send `req`. For sendKey requests pass key='good'|'bad' and level; the key bytes in
        `req` are replaced by a placeholder resolved at run time from the ECU's seed."""
        text = to_hex(req)
        if key is not None:
            lvl = self.p.security_level(level)
            text = to_hex(req[:2]) + (" {KEY:%d}" if key == "good" else " {BADKEY:%d}") % level
            req = req[:2] + bytes(lvl.key_length)
        exp, self.state = self.o.step(req, self.state, key_valid=(key != "bad"))
        self.steps.append(Step(
            n=len(self.steps) + 1, role=role, action="send", request=text,
            expect=exp.kind, expected_pattern=exp.pattern, nrc=exp.nrc, description=desc, rule=exp.rule))
        return exp

    def wait(self, ms: int, desc: str, role: str = "test") -> None:
        self.state = self.o.advance(self.state, ms)
        self.steps.append(Step(n=len(self.steps) + 1, role=role, action="wait", wait_ms=ms,
                               expect="none", description=desc))

    # -- composite helpers (all setup by default) -----------------------------------------------
    def enter(self, session: int, role: str = "setup") -> None:
        if self.state.session != session:
            self.send(bytes([0x10, session]), f"Enter {self.p.session_name(session)}", role)

    def unlock(self, level: int, role: str = "setup") -> None:
        lvl = self.p.security_level(level)
        if level in self.state.unlocked:
            return
        self.send(bytes([0x27, lvl.level]), f"Request seed (level {level})", role)
        self.send(bytes([0x27, lvl.send_key_sub]) + bytes(lvl.key_length),
                  f"Send valid key (level {level})", role, key="good", level=level)

    def alive_wait(self, ms: int, desc: str) -> None:
        """Wait `ms` while keeping the session alive with TesterPresent (if implemented)."""
        chunk = max(self.p.timing.s3_ms // 2, 100)
        remaining = ms
        have_tp = 0x3E in self.p.services
        while remaining > 0:
            step = min(chunk, remaining) if have_tp else remaining
            self.wait(step, desc)
            remaining -= step
            if have_tp and remaining > 0:
                self.send(bytes([0x3E, 0x00]), "TesterPresent keep-alive")
