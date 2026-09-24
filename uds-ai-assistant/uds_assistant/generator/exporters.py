"""Export approved test cases to automation / documentation formats."""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Iterable

from ..protocol.hexutil import parse_hex
from ..protocol.profile import ECUProfile
from .models import Step, TestCase


def _slug(text: str, n: int = 48) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:n]


# ================================================================================================
# Python / pytest
# ================================================================================================
_PY_HARNESS = r'''
# --------------------------------------------------------------------------------------------
# Harness. Select the target with the UDS_TARGET environment variable:
#   UDS_TARGET=sim            in-process mock ECU (needs `pip install -e .` of uds-ai-assistant)
#   UDS_TARGET=can:can0       Linux SocketCAN ISO-TP bench (needs `pip install can-isotp`)
# --------------------------------------------------------------------------------------------
import os
import re

import pytest

PROFILE_JSON = r"""__PROFILE_JSON__"""
REQUEST_ID = __REQ_ID__
RESPONSE_ID = __RESP_ID__
SECURITY = __SECURITY__


def _hex(text: str) -> bytes:
    return bytes.fromhex(re.sub(r"[^0-9A-Fa-f]", "", text))


def _fmt(data) -> str:
    return "<no response>" if data is None else " ".join(f"{b:02X}" for b in data)


def _match(pattern: str, data) -> bool:
    if data is None:
        return pattern.strip() == ""
    toks = pattern.split()
    return len(toks) == len(data) and all(t == "??" or int(t, 16) == b for t, b in zip(toks, data))


class _SimTarget:
    def __init__(self):
        from uds_assistant.protocol.profile import ECUProfile
        from uds_assistant.simulator.mock_ecu import MockECU
        faults = [f for f in os.getenv("UDS_FAULTS", "").split(",") if f]
        self.ecu = MockECU(ECUProfile.model_validate_json(PROFILE_JSON), faults=faults)

    def request(self, data):
        return self.ecu.process(data)

    def wait(self, ms):
        self.ecu.advance(ms)

    def reset(self):
        self.ecu.reset()


class _IsoTpTarget:
    def __init__(self, iface):
        import isotp  # pip install can-isotp (Linux SocketCAN)
        self.s = isotp.socket()
        self.s.bind(iface, isotp.Address(rxid=RESPONSE_ID, txid=REQUEST_ID))

    def request(self, data, timeout=5.0):
        import time
        self.s.send(data)
        frames, end = [], time.monotonic() + timeout
        while time.monotonic() < end:
            self.s.settimeout(max(end - time.monotonic(), 0.01))
            f = self.s.recv()
            if f is None:
                break
            frames.append(bytes(f))
            if not (len(f) == 3 and f[0] == 0x7F and f[2] == 0x78):
                break
        return frames

    def wait(self, ms):
        import time
        time.sleep(ms / 1000)

    def reset(self):
        self.request(b"\x10\x01")


def _make_target():
    kind = os.getenv("UDS_TARGET", "sim")
    if kind == "sim":
        return _SimTarget()
    if kind.startswith("can:"):
        return _IsoTpTarget(kind.split(":", 1)[1])
    raise RuntimeError(f"unknown UDS_TARGET {kind!r}")


class Ctx:
    def __init__(self, target):
        self.t = target
        self.seeds = {}

    def _key(self, kind, level):
        cfg = SECURITY[int(level)]
        seed = self.seeds.get(int(level), bytes(cfg["key_length"]))
        const = cfg["constant"].to_bytes(cfg["key_length"], "big")
        key = bytes(s ^ c for s, c in zip(seed.ljust(cfg["key_length"], b"\0"), const))
        if kind == "BADKEY":
            key = key[:-1] + bytes([key[-1] ^ 0xFF])
        return " ".join(f"{b:02X}" for b in key)

    def send(self, request, expect="", role="test", desc=""):
        req = _hex(re.sub(r"\{(KEY|BADKEY):(\d+)\}", lambda m: self._key(m.group(1), m.group(2)), request))
        final, frames = None, self.t.request(req)
        for f in frames:
            if not (len(f) == 3 and f[0] == 0x7F and f[2] == 0x78):
                final = f
        if req[0] == 0x27 and final and final[0] == 0x67:
            for lvl, cfg in SECURITY.items():
                if req[1] & 0x7F == lvl and len(final) == 2 + cfg["seed_length"]:
                    self.seeds[lvl] = bytes(final[2:])
        if role == "cleanup":
            return
        ok = _match(expect, final)
        assert ok, (f"{'SETUP FAILED: ' if role == 'setup' else ''}{desc}: sent {_fmt(req)}, "
                    f"expected {expect or '<no response>'}, got {_fmt(final)}")

    def wait(self, ms):
        self.t.wait(ms)


@pytest.fixture
def ctx():
    target = _make_target()
    target.reset()
    return Ctx(target)
'''


def export_python(profile: ECUProfile, tests: Iterable[TestCase]) -> str:
    sec = {
        s.level: {"key_length": s.key_length, "seed_length": s.seed_length, "constant": s.constant}
        for s in profile.security_levels
    }
    head = (_PY_HARNESS
            .replace("__PROFILE_JSON__", profile.model_dump_json())
            .replace("__REQ_ID__", hex(profile.request_id))
            .replace("__RESP_ID__", hex(profile.response_id))
            .replace("__SECURITY__", repr(sec)))
    out = [f'"""Generated UDS tests for {profile.name} ({profile.oem}). Review before running on hardware."""',
           head, ""]
    used: set[str] = set()
    for tc in tests:
        name = f"test_{_slug(tc.id, 20)}_{_slug(tc.title, 40)}"
        while name in used:
            name += "_x"
        used.add(name)
        out.append(f"\ndef {name}(ctx, record_property):")
        out.append(f'    """{tc.id}: {tc.title}\n\n    {tc.objective}\n    """')
        if tc.requirement_id:
            out.append(f"    record_property('requirement', {tc.requirement_id!r})")
        out.append(f"    record_property('covers', {','.join(tc.covers)!r})")
        for s in tc.steps:
            if s.action == "wait":
                out.append(f"    ctx.wait({s.wait_ms})  # {s.description}")
            else:
                out.append(f"    ctx.send({s.request!r}, expect={s.expected_pattern!r}, role={s.role!r}, "
                           f"desc={s.description!r})")
    return "\n".join(out) + "\n"


# ================================================================================================
# CAPL (CANoe test module template)
# ================================================================================================
def _carr(name: str, data: bytes) -> str:
    body = ", ".join(f"0x{b:02X}" for b in data)
    return f"byte {name}[{len(data)}] = {{{body}}};"


def export_capl(profile: ECUProfile, tests: Iterable[TestCase]) -> dict[str, str]:
    """Return {filename: content}. The .can file is a CANoe test-module template that calls helper
    procedures declared in ``uds_helpers.cin``; bind those helpers to your project's diagnostic
    layer. Not verified inside CANoe by this project."""
    lines = [
        "/*@!Encoding:1252*/",
        f"/* Generated UDS test module for {profile.name} ({profile.oem}). Review before execution. */",
        "includes",
        "{",
        '  #include "uds_helpers.cin"',
        "}",
        "",
        "variables",
        "{",
        f"  const dword kReqId = 0x{profile.request_id:X};",
        f"  const dword kRespId = 0x{profile.response_id:X};",
        "}",
        "",
    ]
    for tc in tests:
        fn = "TC_" + re.sub(r"[^0-9A-Za-z]", "_", tc.id) + "_" + _slug(tc.title, 32)
        lines += [f"testcase {fn}()", "{",
                  f'  testCaseTitle("{tc.id}", "{tc.title}");',
                  f'  testCaseDescription("{tc.objective}");', "  UdsResetEcu();"]
        for s in tc.steps:
            if s.action == "wait":
                lines.append(f"  UdsWait({s.wait_ms});  // {s.description}")
                continue
            lines.append("  {")
            m = re.fullmatch(r"\s*27\s+([0-9A-Fa-f]{2})\s+\{(KEY|BADKEY):(\d+)\}\s*", s.request)
            if m:
                valid = 1 if m.group(2) == "KEY" else 0
                expect = 1 if s.expect == "positive" else 0
                nrc = s.nrc if s.nrc is not None else 0
                lines.append(f'    UdsSendKey({int(m.group(3))}, 0x{m.group(1).upper()}, {valid}, {expect}, '
                             f'0x{nrc:02X}, "{s.description}");')
            else:
                req = parse_hex(s.request)
                lines.append("    " + _carr("req", req))
                if s.expect == "none":
                    lines.append(f'    UdsExpectNoResponse(req, {len(req)}, "{s.description}");')
                else:
                    toks = s.expected_pattern.split()
                    exp = bytes(0 if t == "??" else int(t, 16) for t in toks)
                    msk = bytes(0 if t == "??" else 0xFF for t in toks)
                    lines.append("    " + _carr("exp", exp))
                    lines.append("    " + _carr("msk", msk))
                    lines.append(f'    UdsExpect(req, {len(req)}, exp, msk, {len(exp)}, "{s.description}", '
                                 f'{1 if s.role == "cleanup" else 0});')
            lines.append("  }")
        lines += ["}", ""]
    can = "\n".join(lines)

    sec_cases = "\n".join(
        f"    case {s.level}: constant = 0x{s.constant:08X}; break;" for s in profile.security_levels)
    helpers = f"""/*@!Encoding:1252*/
/* uds_helpers.cin - STUB. Bind these procedures to your CANoe diagnostic setup.
 *
 * Suggested mapping (adapt to your project):
 *   UdsResetEcu()          send 10 01 (or restart the simulation node) before every test case
 *   UdsWait(ms)            testWaitForTimeout(ms)
 *   UdsExpect(...)         send `req` on kReqId, wait up to P2*/P2 for a response on kRespId, skip pending
 *                          frames (7F <SID> 78), compare byte-wise using `msk` (0x00 = wildcard byte),
 *                          then testStepPass / testStepFail with `desc`
 *   UdsExpectNoResponse    same, but pass only if nothing arrives within the wait window
 *   UdsSendKey             request seed result stored by UdsExpect for the level; key = seed XOR constant
 *                          (algorithm below, matches the profile); invalid key = valid key with last byte inverted
 */
variables
{{
  byte gLastSeed[4];
}}

void UdsResetEcu() {{ /* TODO */ }}
void UdsWait(long ms) {{ testWaitForTimeout(ms); }}
void UdsExpect(byte req[], long reqLen, byte exp[], byte msk[], long expLen, char desc[], int isCleanup) {{ /* TODO */ }}
void UdsExpectNoResponse(byte req[], long reqLen, char desc[]) {{ /* TODO */ }}

dword UdsKeyConstant(int level)
{{
  dword constant;
  switch (level)
  {{
{sec_cases}
    default: constant = 0; break;
  }}
  return constant;
}}

void UdsSendKey(int level, byte sendKeySub, int validKey, int expectPositive, byte expectNrc, char desc[])
{{
  /* TODO: build 27 <sendKeySub> <key>, key = gLastSeed XOR UdsKeyConstant(level) (big-endian);
     if validKey == 0 invert the last key byte; then evaluate like UdsExpect. */
}}
"""
    return {"uds_tests.can": can, "uds_helpers.cin": helpers}


# ================================================================================================
# JSON / CSV / Markdown
# ================================================================================================
def export_json(tests: Iterable[TestCase]) -> str:
    return json.dumps([t.model_dump() for t in tests], indent=2)


def export_csv(tests: Iterable[TestCase]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["TestID", "Title", "Category", "Service", "Requirement", "Status", "Preconditions", "Steps",
                "Expected", "Covers"])
    for t in tests:
        sends = [s for s in t.steps if s.action == "send"]
        steps = "\n".join(f"{s.n}. [{s.role}] {s.request}  ({s.description})" if s.action == "send"
                          else f"{s.n}. wait {s.wait_ms} ms" for s in t.steps)
        expected = "\n".join(f"{s.n}. {s.expected_pattern or 'no response'}" for s in sends if s.role != "cleanup")
        w.writerow([t.id, t.title, t.category, f"0x{t.service:02X}", t.requirement_id or "", t.status,
                    "\n".join(t.preconditions), steps, expected, ";".join(t.covers)])
    return buf.getvalue()


def export_markdown(profile: ECUProfile, tests: Iterable[TestCase]) -> str:
    tests = list(tests)
    out = [f"# UDS test specification - {profile.name}", "",
           f"ECU: {profile.name} ({profile.oem}), profile version {profile.version}. {len(tests)} test case(s).", ""]
    for t in tests:
        out += [f"## {t.id} - {t.title}", "",
                f"*Category:* {t.category} | *Service:* 0x{t.service:02X} | *Status:* {t.status}"
                + (f" | *Requirement:* {t.requirement_id}" if t.requirement_id else ""), "",
                t.objective, "", "| # | Role | Request | Expected | Description |", "|---|---|---|---|---|"]
        for s in t.steps:
            if s.action == "wait":
                out.append(f"| {s.n} | {s.role} | wait {s.wait_ms} ms | - | {s.description} |")
            else:
                out.append(f"| {s.n} | {s.role} | `{s.request}` | `{s.expected_pattern or 'no response'}` | "
                           f"{s.description} |")
        out.append("")
    return "\n".join(out)


def export_all(fmt: str, profile: ECUProfile, tests: list[TestCase]) -> dict[str, str]:
    fmt = fmt.lower()
    if fmt == "python":
        return {"test_uds_generated.py": export_python(profile, tests)}
    if fmt == "capl":
        return export_capl(profile, tests)
    if fmt == "json":
        return {"test_cases.json": export_json(tests)}
    if fmt == "csv":
        return {"test_cases.csv": export_csv(tests)}
    if fmt == "markdown":
        return {"test_specification.md": export_markdown(profile, tests)}
    raise ValueError(f"unknown export format {fmt!r}")
