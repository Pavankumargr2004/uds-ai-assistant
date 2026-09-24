"""Hex parsing / formatting and wildcard pattern matching."""
from __future__ import annotations

import re

_PLACEHOLDER = re.compile(r"\{[A-Z]+:[0-9A-Za-z]+\}")


def parse_hex(text: str) -> bytes:
    """Parse '22 F1 90', '22F190', '0x22 0xF1 0x90' or '22,F1,90' into bytes."""
    if isinstance(text, (bytes, bytearray)):
        return bytes(text)
    cleaned = re.sub(r"0x", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\s,;:_-]+", "", cleaned)
    if cleaned == "":
        return b""
    if len(cleaned) % 2 or not re.fullmatch(r"[0-9A-Fa-f]+", cleaned):
        raise ValueError(f"Not a valid hex string: {text!r}")
    return bytes.fromhex(cleaned)


def to_hex(data: bytes | None) -> str:
    if data is None:
        return ""
    return " ".join(f"{b:02X}" for b in data)


def has_placeholder(text: str) -> bool:
    return bool(_PLACEHOLDER.search(text))


def match_pattern(pattern: str, data: bytes | None) -> bool:
    """Match bytes against a pattern such as '62 F1 90 ?? ??'. '??' matches any byte."""
    if data is None:
        return pattern.strip() == ""
    tokens = pattern.split()
    if len(tokens) != len(data):
        return False
    for tok, b in zip(tokens, data):
        if tok == "??":
            continue
        if int(tok, 16) != b:
            return False
    return True
