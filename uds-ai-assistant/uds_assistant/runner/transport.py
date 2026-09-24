"""Transports: how requests reach an ECU.

* ``SimTransport``  - in-process mock ECU with a virtual clock (default, safe).
* ``IsoTpTransport`` - Linux SocketCAN ISO-TP via ``can-isotp`` (optional dependency).
  NOTE: written against the public can-isotp socket API but NOT verified against hardware
  in this repository's CI. Treat it as a starting point for your bench.

All transports return the list of frames the ECU sent for one request; NRC 0x78
("response pending") frames may precede the final frame.
"""
from __future__ import annotations

import time
from typing import Protocol

from ..protocol.profile import ECUProfile
from ..simulator.mock_ecu import MockECU


class Transport(Protocol):
    def request(self, data: bytes, timeout_ms: int = 5000) -> list[bytes]: ...
    def wait(self, ms: int) -> None: ...
    def reset(self) -> None: ...
    def close(self) -> None: ...
    @property
    def now_ms(self) -> int: ...


class SimTransport:
    kind = "simulator"

    def __init__(self, profile: ECUProfile, faults=()):
        self.ecu = MockECU(profile, faults=faults)

    def request(self, data: bytes, timeout_ms: int = 5000) -> list[bytes]:
        return self.ecu.process(data)

    def wait(self, ms: int) -> None:
        self.ecu.advance(ms)

    def reset(self) -> None:
        self.ecu.reset()

    def close(self) -> None:
        pass

    @property
    def now_ms(self) -> int:
        return self.ecu.now_ms


class IsoTpTransport:  # pragma: no cover - needs SocketCAN hardware / vcan
    kind = "hardware"

    def __init__(self, interface: str, tx_id: int, rx_id: int):
        try:
            import isotp  # type: ignore
        except ImportError as e:
            raise RuntimeError("Install 'can-isotp' (pip install can-isotp) and use Linux SocketCAN") from e
        self._isotp = isotp
        self._sock = isotp.socket()
        self._sock.set_opts(txpad=0xAA, rxpad=0xAA)
        self._sock.bind(interface, isotp.Address(rxid=rx_id, txid=tx_id))
        self._t0 = time.monotonic()

    def request(self, data: bytes, timeout_ms: int = 5000) -> list[bytes]:
        self._sock.send(data)
        frames: list[bytes] = []
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            self._sock.settimeout(max(deadline - time.monotonic(), 0.01))
            try:
                frame = self._sock.recv()
            except Exception:
                break
            if frame is None:
                break
            frames.append(bytes(frame))
            if not (len(frame) == 3 and frame[0] == 0x7F and frame[2] == 0x78):
                break
        return frames

    def wait(self, ms: int) -> None:
        time.sleep(ms / 1000)

    def reset(self) -> None:
        self.request(bytes([0x10, 0x01]), timeout_ms=1000)

    def close(self) -> None:
        self._sock.close()

    @property
    def now_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)


class SafetyGuard:
    """Refuses unsafe execution. Simulator runs are always allowed; hardware runs need explicit opt-in."""

    ALWAYS_BLOCKED = {0x34, 0x35, 0x36, 0x37, 0x38, 0x3D}          # download / upload / transfer / flash
    STATE_CHANGING = {0x10, 0x11, 0x14, 0x28, 0x2E, 0x31, 0x85}

    def __init__(self, allow_hardware: bool = False, target_environment: str = "simulator",
                 allow_state_changing: bool = False):
        self.allow_hardware = allow_hardware
        self.env = target_environment
        self.allow_state_changing = allow_state_changing

    def check(self, transport_kind: str, tests) -> list[str]:
        problems: list[str] = []
        if transport_kind == "simulator":
            return problems
        if not self.allow_hardware:
            problems.append("hardware execution disabled (set UDS_ALLOW_HARDWARE=1)")
        if self.env != "bench":
            problems.append(f"target environment is '{self.env}', hardware runs require 'bench' (UDS_TARGET_ENV=bench)")
        sids = {int(s.request.split()[0], 16) for t in tests for s in t.steps if s.action == "send" and s.request}
        blocked = sids & self.ALWAYS_BLOCKED
        if blocked:
            problems.append("blocked services in test set: " + ", ".join(f"0x{s:02X}" for s in sorted(blocked)))
        risky = sids & self.STATE_CHANGING - {0x10}
        if risky and not self.allow_state_changing:
            problems.append("state-changing services need UDS_HW_ALLOW_STATE_CHANGING=1: "
                            + ", ".join(f"0x{s:02X}" for s in sorted(risky)))
        return problems
