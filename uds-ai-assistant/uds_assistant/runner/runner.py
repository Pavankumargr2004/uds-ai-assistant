"""Executes test cases against a transport and evaluates every step."""
from __future__ import annotations

import re
import time
from typing import Optional

from pydantic import BaseModel, Field

from ..generator.models import Step, TestCase
from ..protocol.hexutil import match_pattern, parse_hex, to_hex
from ..protocol.nrc import nrc_name
from ..protocol.profile import ECUProfile
from .transport import Transport

_PH = re.compile(r"\{(KEY|BADKEY):(\d+)\}")


class StepResult(BaseModel):
    n: int
    role: str
    action: str
    request: str = ""
    response: Optional[str] = None
    pending_frames: int = 0
    expected: str = ""
    expect: str = ""
    passed: bool = True
    message: str = ""
    t_ms: int = 0


class TestResult(BaseModel):
    __test__ = False
    test_id: str
    title: str = ""
    category: str = ""
    service: int = 0
    verdict: str = "pass"            # pass | fail | error
    steps: list[StepResult] = Field(default_factory=list)
    message: str = ""
    covers: list[str] = Field(default_factory=list)


class RunSummary(BaseModel):
    target: str = "simulator"
    faults: list[str] = Field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    pass_rate: float = 0.0
    duration_s: float = 0.0
    results: list[TestResult] = Field(default_factory=list)

    def failures(self) -> list[TestResult]:
        return [r for r in self.results if r.verdict != "pass"]


class Runner:
    def __init__(self, profile: ECUProfile, transport: Transport):
        self.p = profile
        self.t = transport

    # -- placeholder resolution ------------------------------------------------------------------
    def _resolve(self, text: str, seeds: dict[int, bytes]) -> bytes:
        def sub(m: re.Match) -> str:
            kind, level = m.group(1), int(m.group(2))
            lvl = self.p.security_level(level)
            if lvl is None:
                raise ValueError(f"unknown security level {level}")
            seed = seeds.get(level)
            if seed is None:
                return to_hex(bytes(lvl.key_length))
            return to_hex(lvl.compute_key(seed) if kind == "KEY" else lvl.bad_key(seed))
        return parse_hex(_PH.sub(sub, text))

    def _exchange(self, req: bytes) -> tuple[Optional[bytes], int]:
        frames = self.t.request(req)
        pending = 0
        final: Optional[bytes] = None
        for f in frames:
            if len(f) == 3 and f[0] == 0x7F and f[2] == 0x78 and f[1] == req[0]:
                pending += 1
                continue
            final = f
        return final, pending

    # -- execution ---------------------------------------------------------------------------------
    def run_test(self, tc: TestCase) -> TestResult:
        res = TestResult(test_id=tc.id, title=tc.title, category=tc.category, service=tc.service, covers=tc.covers)
        self.t.reset()
        seeds: dict[int, bytes] = {}
        for step in tc.steps:
            sr = StepResult(n=step.n, role=step.role, action=step.action, request=step.request,
                            expected=step.expected_pattern, expect=step.expect)
            try:
                if step.action == "wait":
                    self.t.wait(step.wait_ms)
                    sr.message = f"waited {step.wait_ms} ms"
                    sr.t_ms = self.t.now_ms
                    res.steps.append(sr)
                    continue
                req = self._resolve(step.request, seeds)
                sr.request = to_hex(req)
                resp, pending = self._exchange(req)
                sr.response = to_hex(resp) if resp is not None else None
                sr.pending_frames = pending
                sr.t_ms = self.t.now_ms
                self._learn_seed(req, resp, seeds)
                sr.passed, sr.message = self._judge(step, resp)
            except Exception as e:  # transport / resolution error
                sr.passed, sr.message = False, f"error: {e}"
                res.steps.append(sr)
                res.verdict, res.message = "error", f"step {step.n}: {e}"
                return res
            res.steps.append(sr)
            if not sr.passed and step.role != "cleanup":
                if step.role == "setup":
                    res.verdict, res.message = "error", f"setup step {step.n} failed: {sr.message}"
                else:
                    res.verdict, res.message = "fail", f"step {step.n} failed: {sr.message}"
                return res
        return res

    def _learn_seed(self, req: bytes, resp: Optional[bytes], seeds: dict[int, bytes]) -> None:
        if req[0] == 0x27 and resp and resp[0] == 0x67 and len(req) >= 2:
            lvl, kind = self.p.security_by_sub(req[1] & 0x7F)
            if lvl and kind == "seed" and len(resp) >= 2 + lvl.seed_length:
                seeds[lvl.level] = resp[2:2 + lvl.seed_length]

    def _judge(self, step: Step, resp: Optional[bytes]) -> tuple[bool, str]:
        if step.expect == "none":
            if resp is None:
                return True, "no response, as expected"
            return False, f"expected no response, got {to_hex(resp)}"
        if resp is None:
            return False, f"no response (expected {step.expected_pattern})"
        if match_pattern(step.expected_pattern, resp):
            return True, "ok"
        if len(resp) == 3 and resp[0] == 0x7F:
            got = f"NRC 0x{resp[2]:02X} {nrc_name(resp[2])}"
        else:
            got = to_hex(resp)
        want = (f"NRC 0x{step.nrc:02X} {nrc_name(step.nrc)}" if step.nrc is not None else step.expected_pattern)
        return False, f"expected {want}, got {got}"

    def run(self, tests: list[TestCase], faults: Optional[list[str]] = None) -> RunSummary:
        t0 = time.time()
        summary = RunSummary(target=getattr(self.t, "kind", "unknown"), faults=list(faults or []))
        for tc in tests:
            r = self.run_test(tc)
            summary.results.append(r)
        summary.total = len(summary.results)
        summary.passed = sum(r.verdict == "pass" for r in summary.results)
        summary.failed = sum(r.verdict == "fail" for r in summary.results)
        summary.errors = sum(r.verdict == "error" for r in summary.results)
        summary.pass_rate = round(100.0 * summary.passed / summary.total, 1) if summary.total else 0.0
        summary.duration_s = round(time.time() - t0, 3)
        return summary

    def run_stream(self, tests: list[TestCase], faults: Optional[list[str]] = None):
        t0 = time.time()
        summary = RunSummary(target=getattr(self.t, "kind", "unknown"), faults=list(faults or []))
        for tc in tests:
            r = self.run_test(tc)
            summary.results.append(r)
            yield r
        summary.total = len(summary.results)
        summary.passed = sum(r.verdict == "pass" for r in summary.results)
        summary.failed = sum(r.verdict == "fail" for r in summary.results)
        summary.errors = sum(r.verdict == "error" for r in summary.results)
        summary.pass_rate = round(100.0 * summary.passed / summary.total, 1) if summary.total else 0.0
        summary.duration_s = round(time.time() - t0, 3)
        yield summary

