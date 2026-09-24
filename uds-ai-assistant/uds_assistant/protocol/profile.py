"""ECU diagnostic profile: the machine-readable, authorised project extract.

A profile is the single source of truth for what *this* ECU implements: sessions,
services, sub-functions, DIDs, routines, DTCs, security levels and timing.
It is loaded from YAML and validated with pydantic.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Literal, Optional

import yaml
from pydantic import BaseModel, BeforeValidator, Field, model_validator


def _to_int(v):
    if isinstance(v, bool):
        raise ValueError("bool is not an integer")
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        return int(v.strip(), 0)
    raise ValueError(f"cannot convert {v!r} to int")


HexInt = Annotated[int, BeforeValidator(_to_int)]

SESSION_DEFAULT = 0x01
SESSION_PROGRAMMING = 0x02
SESSION_EXTENDED = 0x03
SESSION_NAMES = {0x01: "defaultSession", 0x02: "programmingSession", 0x03: "extendedDiagnosticSession"}


class Access(BaseModel):
    sessions: list[HexInt]
    security: Optional[HexInt] = None  # required security level, None = no unlock needed


class SubFunctionDef(BaseModel):
    name: str
    sessions: Optional[list[HexInt]] = None  # None = same as the service


class ServiceDef(BaseModel):
    name: str
    sessions: list[HexInt]
    security: Optional[HexInt] = None
    subfunctions: dict[HexInt, SubFunctionDef] = Field(default_factory=dict)
    notes: str = ""


class DidDef(BaseModel):
    id: HexInt
    name: str
    length: int
    data_type: Literal["ascii", "uint", "bytes"] = "bytes"
    default: Optional[str | int] = None
    example: Optional[str | int] = None
    invalid_example: Optional[str | int] = None
    min: Optional[int] = None
    max: Optional[int] = None
    pattern: Optional[str] = None
    read: Optional[Access] = None
    write: Optional[Access] = None
    live: Optional[str] = None  # e.g. "active_session": value computed by the ECU
    description: str = ""

    def encode(self, value: str | int | None) -> bytes:
        if value is None:
            return bytes(self.length)
        if self.data_type == "ascii":
            raw = str(value).encode("ascii")
            return raw.ljust(self.length, b" ")[: self.length]
        if self.data_type == "uint":
            return int(value).to_bytes(self.length, "big")
        return bytes.fromhex(str(value).replace(" ", "")).ljust(self.length, b"\x00")[: self.length]

    def default_bytes(self) -> bytes:
        return self.encode(self.default)

    def example_bytes(self) -> bytes:
        return self.encode(self.example if self.example is not None else self.default)

    def value_error(self, data: bytes) -> Optional[str]:
        """Return a reason string if `data` is not an acceptable value, else None."""
        if self.data_type == "uint":
            n = int.from_bytes(data, "big")
            if self.min is not None and n < self.min:
                return f"value {n} below minimum {self.min}"
            if self.max is not None and n > self.max:
                return f"value {n} above maximum {self.max}"
        if self.data_type == "ascii" and self.pattern:
            try:
                text = data.decode("ascii")
            except UnicodeDecodeError:
                return "non-ASCII data"
            if not re.fullmatch(self.pattern, text):
                return f"value {text!r} does not match pattern {self.pattern}"
        return None


class RoutineDef(BaseModel):
    id: HexInt
    name: str
    sessions: list[HexInt]
    security: Optional[HexInt] = None
    subfunctions: list[HexInt] = Field(default_factory=lambda: [1, 2, 3])
    option_length: int = 0  # bytes of routineControlOptionRecord for start
    start_response: str = ""   # hex bytes appended to the positive response
    stop_response: str = ""
    results_response: str = ""
    single_instance: bool = True
    send_pending: bool = False  # simulator: emit NRC 0x78 before the final response
    description: str = ""

    def resp_bytes(self, sub: int) -> bytes:
        hexstr = {1: self.start_response, 2: self.stop_response, 3: self.results_response}[sub]
        return bytes.fromhex(hexstr.replace(" ", ""))


class DtcDef(BaseModel):
    code: HexInt  # 3-byte DTC
    status: HexInt
    name: str = ""


class SecurityLevel(BaseModel):
    level: HexInt  # equals the requestSeed sub-function
    send_key_sub: HexInt
    seed_length: int = 4
    key_length: int = 4
    algorithm: Literal["xor"] = "xor"
    constant: HexInt
    max_attempts: int = 3
    lockout_ms: int = 10000
    description: str = ""

    def compute_key(self, seed: bytes) -> bytes:
        const = self.constant.to_bytes(self.key_length, "big")
        return bytes(s ^ c for s, c in zip(seed.ljust(self.key_length, b"\0"), const))

    def bad_key(self, seed: bytes) -> bytes:
        good = bytearray(self.compute_key(seed))
        good[-1] ^= 0xFF
        return bytes(good)


class Timing(BaseModel):
    p2_ms: int = 50
    p2_star_ms: int = 5000
    s3_ms: int = 5000


class ECUProfile(BaseModel):
    name: str
    oem: str = ""
    version: str = "1.0"
    description: str = ""
    request_id: HexInt = 0x7E0
    response_id: HexInt = 0x7E8
    timing: Timing = Field(default_factory=Timing)
    sessions: dict[HexInt, str] = Field(default_factory=lambda: dict(SESSION_NAMES))
    services: dict[HexInt, ServiceDef]
    dids: list[DidDef] = Field(default_factory=list)
    routines: list[RoutineDef] = Field(default_factory=list)
    dtcs: list[DtcDef] = Field(default_factory=list)
    security_levels: list[SecurityLevel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self):
        ids = [d.id for d in self.dids]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate DID id in profile")
        rids = [r.id for r in self.routines]
        if len(rids) != len(set(rids)):
            raise ValueError("duplicate RID id in profile")
        levels = {s.level for s in self.security_levels}
        for d in self.dids:
            for acc in (d.read, d.write):
                if acc and acc.security is not None and acc.security not in levels:
                    raise ValueError(f"DID 0x{d.id:04X} references unknown security level {acc.security}")
        for r in self.routines:
            if r.security is not None and r.security not in levels:
                raise ValueError(f"RID 0x{r.id:04X} references unknown security level {r.security}")
        return self

    # -- lookups --------------------------------------------------------------------------
    def did(self, did_id: int) -> Optional[DidDef]:
        return next((d for d in self.dids if d.id == did_id), None)

    def routine(self, rid: int) -> Optional[RoutineDef]:
        return next((r for r in self.routines if r.id == rid), None)

    def security_level(self, level: int) -> Optional[SecurityLevel]:
        return next((s for s in self.security_levels if s.level == level), None)

    def security_by_sub(self, sub: int) -> tuple[Optional[SecurityLevel], Optional[str]]:
        """Map a 0x27 sub-function to (level, 'seed'|'key')."""
        for s in self.security_levels:
            if sub == s.level:
                return s, "seed"
            if sub == s.send_key_sub:
                return s, "key"
        return None, None

    def session_name(self, s: int) -> str:
        return self.sessions.get(s, f"session0x{s:02X}")

    @property
    def readable_dids(self) -> list[DidDef]:
        return [d for d in self.dids if d.read]

    @property
    def writable_dids(self) -> list[DidDef]:
        return [d for d in self.dids if d.write]


def load_profile(path: str | Path) -> ECUProfile:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return ECUProfile.model_validate(data)


def parse_profile(text: str) -> ECUProfile:
    return ECUProfile.model_validate(yaml.safe_load(text))
